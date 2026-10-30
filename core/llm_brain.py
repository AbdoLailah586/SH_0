"""
AI Smart Home LLM Brain & Tool-Calling Orchestrator.
Dual Provider Architecture:
  1. Primary: Groq LPU (llama-3.3-70b-versatile) - Ultra-low latency (<250ms)
  2. Automatic Fallback: OpenRouter (:free models) - Instant failover if Groq 429/offline
Features:
  - Full Function/Tool Calling for ESP32 and Laptop OS Controls
  - Egyptian Arabic Persona (ar-EG) returning concise, witty 1-sentence spoken replies
"""

import json
import os
import time
from typing import Dict, Any, List, Optional, Tuple, Callable
import requests

from core.paths import resolve_path


SYSTEM_PROMPT = """أنت "هوم هب" (HomeHub)، المساعد الصوتي المصري الذكي للسمارت هوم واللابتوب.
قواعد الرد الصارمة:
1. رد دائماً بالعامية المصرية الطبيعية والمهذبة (مثال: "من عنيا"، "تمام يا فندم"، "حاضر يا غالي"، "يا سيدي").
2. اجعل ردك الصوتي قصيراً ومختصراً جداً (جملة واحدة فقط أو جملتين كحد أقصى) لكي يتم نطقه فوراً بدون ثرثرة.
3. إذا طلب المستخدم أمراً واضحاً وصريحاً يتعلق بالمنزل أو اللابتوب (مثل تشغيل نور، تكييف، شباك، صوت، قفل لابتوب، بطارية)، استخدم استدعاء الدوال (Tool Calls) لتنفيذ الأمر فوراً ثم رد بما تم.
4. إذا سأل سؤالاً عاماً أو دردشة أو طلب نكتة أو كم الساعة أو كيف حالك، أجب بخفة دم مصرية وذكاء موجز دون استدعاء أي دوال.
5. ⚠️ قاعدة أمان قصوى وحاسمة: ممنوع تماماً استدعاء أي أداة أو فتح أي تطبيق أو تشغيل أي جهاز إذا كان كلام المستخدم غير واضح تماماً، أو مشوشاً، أو يحتوي على كلمات غريبة أو غير مفهومة (مثل أصوات تشويش أو كلمات مقطوعة). لا تخمن نية المستخدم إطلاقاً عند الغموض، بل رد بالدردشة بلباقة: "معلش مسمعتكش كويس، ممكن تقول تاني؟" أو "كلامك مكنش واضح يا فندم، قصدك إيه؟".
"""

SMART_HOME_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "control_esp32",
            "description": "التحكم في أجهزة وإضاءة المنزل المتصلة ببوردة ESP32. استخدم هذه الدالة فقط وحصرياً إذا كان المستخدم يطلب بوضوح تام التحكم في الإضاءة أو التكييف أو الشباك أو الريلاي. لا تستدعها إطلاقاً في الكلام الغامض أو الدردشة.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["relay", "led", "all_lights", "ac", "window"],
                        "description": "نوع الجهاز المطلوب التحكم به"
                    },
                    "channel": {
                        "type": "integer",
                        "description": "رقم القناة للريلاي (1 للريسبشن، 2 لغرفة النوم، 3 للمروحة، 4 إضافي)",
                        "enum": [1, 2, 3, 4]
                    },
                    "state": {
                        "type": "string",
                        "enum": ["on", "off", "toggle"],
                        "description": "الحالة المطلوبة (تشغيل/إطفاء/تبديل)"
                    },
                    "value": {
                        "type": "integer",
                        "description": "قيمة رقمية (مثل درجة التكييف من 16 إلى 30، أو نسبة فتح الشباك من 0 إلى 100)"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_laptop",
            "description": "التحكم في نظام تشغيل ويندوز باللابتوب. استخدم هذه الدالة فقط وحصرياً إذا طلب المستخدم صراحة أمر تحكم في اللابتوب (مثل قفل الشاشة، رفع/خفض الصوت، فتح تطبيق محدد بالاسم، فحص البطارية). لا تستدعها إطلاقاً إذا كان الكلام غير مفهوم أو دردشة عادية.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": [
                            "volume_up", "volume_down", "mute", "lock_screen",
                            "turn_off_screen", "play_pause", "next_track",
                            "prev_track", "get_battery", "get_stats", "launch_app"
                        ],
                        "description": "الأمر المراد تنفيذه على اللابتوب"
                    },
                    "app_name": {
                        "type": "string",
                        "description": "اسم التطبيق المراد فتحه مثل chrome, spotify, notepad, code"
                    },
                    "step": {
                        "type": "integer",
                        "description": "مقدار رفع أو خفض الصوت بالنسبة المئوية (افتراضي 15)"
                    }
                },
                "required": ["command"]
            }
        }
    }
]


class LLMBrain:
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        openrouter_api_key: Optional[str] = None
    ):
        self.settings_file = resolve_path("config/app_settings.json")
        self.groq_api_key = groq_api_key
        self.openrouter_api_key = openrouter_api_key
        self._load_keys_from_settings()

        self.groq_model = "qwen/qwen3.8-27b"
        self.groq_fallback_models = ["qwen/qwen3.8-27b", "allam-2-7b", "llama-3.3-70b-versatile"]
        self.openrouter_model = "meta-llama/llama-3.3-70b-instruct:free"

        # Action handlers (bound from MainWindow)
        self.esp32_handler: Optional[Callable[[str, Optional[int], Optional[str], Optional[int]], Any]] = None
        self.laptop_handler: Optional[Callable[[str, Optional[str], Optional[int]], Any]] = None

    def _load_keys_from_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not self.groq_api_key:
                        self.groq_api_key = data.get("groq_api_key", os.environ.get("GROQ_API_KEY", ""))
                    if not self.openrouter_api_key:
                        self.openrouter_api_key = data.get("openrouter_api_key", os.environ.get("OPENROUTER_API_KEY", ""))
            except Exception:
                pass

    def save_keys(self, groq_key: str, openrouter_key: str):
        self.groq_api_key = groq_key.strip()
        self.openrouter_api_key = openrouter_key.strip()
        try:
            settings = {}
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            settings["groq_api_key"] = self.groq_api_key
            settings["openrouter_api_key"] = self.openrouter_api_key
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[LLM Save Keys Error] {e}")

    def call_groq(self, messages: List[Dict[str, Any]]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Calls Groq LPU API (<250ms latency)."""
        if not self.groq_api_key:
            return False, None, "مفتاح Groq API غير مدخل"

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }

        # Try active model first, then fallback models if 404
        candidates = [self.groq_model] + [m for m in self.groq_fallback_models if m != self.groq_model]
        last_err = ""
        for model in candidates:
            payload = {
                "model": model,
                "messages": messages,
                "tools": SMART_HOME_TOOLS,
                "tool_choice": "auto",
                "temperature": 0.4,
                "max_tokens": 150
            }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=4.0)
                if resp.status_code == 200:
                    self.groq_model = model  # cache working model
                    return True, resp.json(), "OK"
                elif resp.status_code == 404:
                    last_err = f"Model {model} not found (404)"
                    continue
                elif resp.status_code == 429:
                    return False, None, "Groq Rate Limit (429)"
                else:
                    return False, None, f"Groq Error {resp.status_code}: {resp.text[:100]}"
            except Exception as e:
                return False, None, f"Groq Exception: {str(e)}"

        return False, None, last_err or "No working Groq model found"

    def call_openrouter(self, messages: List[Dict[str, Any]]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Fallback to OpenRouter (:free model)."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        if self.openrouter_api_key:
            headers["Authorization"] = f"Bearer {self.openrouter_api_key}"

        payload = {
            "model": self.openrouter_model,
            "messages": messages,
            "tools": SMART_HOME_TOOLS,
            "temperature": 0.5,
            "max_tokens": 150
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=6.0)
            if resp.status_code == 200:
                return True, resp.json(), "OK"
            return False, None, f"OpenRouter Error {resp.status_code}: {resp.text[:100]}"
        except Exception as e:
            return False, None, f"OpenRouter Exception: {str(e)}"

    def execute_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Executes hardware or laptop actions triggered by the LLM."""
        try:
            if tool_name == "control_esp32" and self.esp32_handler:
                action = arguments.get("action", "")
                ch = arguments.get("channel")
                state = arguments.get("state", "toggle")
                val = arguments.get("value")
                res = self.esp32_handler(action, ch, state, val)
                return json.dumps({"status": "success", "result": str(res)})

            elif tool_name == "control_laptop" and self.laptop_handler:
                cmd = arguments.get("command", "")
                app = arguments.get("app_name")
                step = arguments.get("step", 15)
                res = self.laptop_handler(cmd, app, step)
                return json.dumps({"status": "success", "result": str(res)})

        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

        return json.dumps({"status": "unknown_tool"})

    def process_user_query(
        self,
        user_text: str,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, List[str], str, float]:
        """
        Main entry point for conversational reasoning and multi-step commands.
        Returns:
            (spoken_arabic_reply, executed_actions_list, provider_used, latency_ms)
        """
        t0 = time.perf_counter()
        import datetime
        now = datetime.datetime.now()
        time_ctx = f"\nمعلومات حية: الساعة الآن {now.strftime('%I:%M')} {'مساءً' if now.hour >= 12 else 'صباحاً'}، والتاريخ اليوم {now.strftime('%Y-%m-%d')}."
        messages = [{"role": "system", "content": SYSTEM_PROMPT + time_ctx}]

        if chat_history:
            messages.extend(chat_history[-4:])

        messages.append({"role": "user", "content": user_text})

        # 1. Try Groq Primary
        success, response_data, reason = self.call_groq(messages)
        provider = "Groq (llama-3.3-70b)"

        # 2. Failover to OpenRouter if Groq unavailable
        if not success:
            print(f"[LLMBrain] Switching to OpenRouter fallback. Reason: {reason}")
            success, response_data, reason = self.call_openrouter(messages)
            provider = "OpenRouter (Free Fallback)"

        if not success or not response_data:
            latency = (time.perf_counter() - t0) * 1000
            return "معلش يا فندم، واجهت مشكلة في الاتصال بالذكاء الاصطناعي، أؤمرني بأي أمر مباشر.", [], "Failed", latency

        choice = response_data.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])
        executed_actions = []

        # Handle Tool Calling
        if tool_calls:
            messages.append(message)
            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except Exception:
                    args = {}

                exec_result = self.execute_tool_call(func_name, args)
                executed_actions.append(f"{func_name}: {args}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "name": func_name,
                    "content": exec_result
                })

            # Get final spoken response from LLM acknowledging the tool execution
            if "Groq" in provider:
                success2, resp2, _ = self.call_groq(messages)
            else:
                success2, resp2, _ = self.call_openrouter(messages)

            if success2 and resp2:
                final_text = resp2.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                final_text = "تمام يا فندم، نفذت طلبك في ثانية!"
        else:
            final_text = message.get("content", "تمام يا فندم.")

        latency = (time.perf_counter() - t0) * 1000
        return final_text.strip(), executed_actions, provider, latency

