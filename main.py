from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At, Plain
import json
import os
import time
from datetime import datetime
from pathlib import Path

@register("welcome_group", "User", "QQ群新人入群自动欢迎插件", "1.0.5", "https://github.com/User/astrbot_plugin_Welcome-group")
class WelcomePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        try:
            from astrbot.api.star import StarTools
            self.data_dir = StarTools.get_data_dir() / "welcome_group"
        except ImportError:
            self.data_dir = Path(os.getcwd()) / "data" / "welcome_group"

        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.data_dir / "config.json"
        self.config = self.load_config()

    def _get_default_config(self):
        return {
            "default_message": "欢迎 {at} 加入本群！当前时间：{time}",
            "default_leave_message": "{user_id} 离开了本群。",
            "default_kick_message": "{user_id} 被移出了本群。",
            "groups": {}
        }

    def load_config(self):
        default_config = self._get_default_config()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # 兼容旧版配置文件：补充缺失的默认字段
                for key, value in default_config.items():
                    if key not in saved:
                        saved[key] = value
                return saved
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                return default_config
        return default_config

    def save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    # ==================== 入群欢迎 ====================

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_increase(self, event: AstrMessageEvent):
        """处理新人入群事件"""
        try:
            # 直接从 event 获取 raw_message
            raw = self._get_raw_message(event)
            
            # 调试日志 - 查看实际接收到的事件
            if raw:
                logger.debug(f"WelcomePlugin: 收到事件 raw = {raw}")
            
            if not raw or not isinstance(raw, dict):
                logger.debug("WelcomePlugin: raw 不是 dict 或为空")
                return None

            post_type = raw.get("post_type")
            notice_type = raw.get("notice_type")
            
            logger.debug(f"WelcomePlugin: post_type={post_type}, notice_type={notice_type}")
            
            if post_type != "notice" or notice_type != "group_increase":
                return None

            group_id = str(raw.get("group_id"))
            user_id = raw.get("user_id")
            self_id = raw.get("self_id")

            logger.info(f"WelcomePlugin: 检测到新人入群 - 群:{group_id}, 用户:{user_id}, 自己:{self_id}")

            # 如果是机器人自己进群，忽略
            if str(user_id) == str(self_id):
                logger.info("WelcomePlugin: 机器人自己入群，忽略")
                return None

            group_config = self.config["groups"].get(group_id)
            if not group_config:
                logger.info(f"WelcomePlugin: 群 {group_id} 未配置，使用默认设置")
                # 自动启用默认配置
                self._ensure_group(group_id)
                self.config["groups"][group_id]["enabled"] = True
                self.config["groups"][group_id]["message"] = self.config["default_message"]
                self.save_config()
                group_config = self.config["groups"][group_id]
            
            if not group_config.get("enabled", False):
                logger.info(f"WelcomePlugin: 群 {group_id} 欢迎功能已关闭")
                return None

            welcome_template = group_config.get("message", self.config["default_message"])
            time_str = self._parse_time(raw)

            processed = welcome_template.replace("{time}", time_str).replace("{user_id}", str(user_id))
            message_list = self._build_onebot_message(processed, user_id)

            logger.info(f"WelcomePlugin: 准备发送入群欢迎 -> 群 {group_id} 用户 {user_id}, 内容: {processed}")

            # 尝试发送
            success = await self._send_group_msg(event, group_id, message_list)
            if not success:
                logger.warning(f"WelcomePlugin: bot.send_group_msg 失败，尝试使用 event.reply")
                # 尝试使用 event.reply 作为备选
                try:
                    chain = self._build_fallback_chain(processed, user_id)
                    # 使用 send 方法
                    if hasattr(event, 'send'):
                        await event.send(chain)
                    elif hasattr(event, 'reply'):
                        await event.reply(chain)
                    logger.info(f"WelcomePlugin: 通过 event.send/reply 发送成功")
                except Exception as e2:
                    logger.error(f"WelcomePlugin: 通过 event.send/reply 也失败了: {e2}")
            
            return None

        except Exception as e:
            logger.error(f"WelcomePlugin: 处理入群事件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        return None

    # ==================== 退群 / 被踢 ====================

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_decrease(self, event: AstrMessageEvent):
        """处理退群 / 被踢出群事件"""
        try:
            raw = self._get_raw_message(event)
            if not isinstance(raw, dict):
                return None

            post_type = raw.get("post_type")
            notice_type = raw.get("notice_type")

            if post_type != "notice" or notice_type != "group_decrease":
                return None

            sub_type = raw.get("sub_type", "")
            group_id = str(raw.get("group_id"))
            user_id = raw.get("user_id")
            self_id = raw.get("self_id")

            # 机器人自己被踢，无法发消息，仅记录日志
            if sub_type == "kick_me" or str(user_id) == str(self_id):
                logger.info(f"WelcomePlugin: 机器人被踢出群 {group_id}，操作者: {raw.get('operator_id')}")
                return None

            group_config = self.config["groups"].get(group_id, {})

            if sub_type == "leave":
                if not group_config.get("leave_enabled", False):
                    return None
                template = group_config.get("leave_message", self.config["default_leave_message"])
                log_label = "退群"
            elif sub_type == "kick":
                if not group_config.get("kick_enabled", False):
                    return None
                template = group_config.get("kick_message", self.config["default_kick_message"])
                log_label = "被踢"
            else:
                return None

            time_str = self._parse_time(raw)
            processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
            message_list = self._build_onebot_message(processed, user_id)

            logger.info(f"WelcomePlugin: 准备发送{log_label}通知 -> 群 {group_id} 用户 {user_id}")

            await self._send_group_msg(event, group_id, message_list)
            return None

        except Exception as e:
            logger.error(f"WelcomePlugin: 处理退群/被踢事件失败: {e}")
        return None

    # ==================== 指令入口 ====================

    @filter.command_group("welcome")
    def welcome_group_cmd(self):
        """群欢迎/退群/踢人通知插件管理"""
        pass

    # ---- 入群欢迎指令 ----

    @welcome_group_cmd.command("set")
    async def set_welcome(self, event: AstrMessageEvent, message: str):
        """设置入群欢迎语。支持变量: {at}, {user_id}, {time}。例如: /welcome set 欢迎 {at} 于 {time} 加入！"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        message = self._get_full_message(event, "set")
        if not message:
            yield event.plain_result("请提供欢迎语内容。例如: /welcome set 欢迎 {at} 加入！")
            return
            
        self._ensure_group(group_id)
        self.config["groups"][group_id]["enabled"] = True
        self.config["groups"][group_id]["message"] = message
        self.save_config()
        yield event.plain_result(f"已设置本群入群欢迎语为：\n{message}")

    @welcome_group_cmd.command("on")
    async def enable_welcome(self, event: AstrMessageEvent):
        """开启当前群的入群欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        self._ensure_group(group_id)
        self.config["groups"][group_id]["enabled"] = True
        self.save_config()
        yield event.plain_result("本群入群欢迎功能已开启。")

    @welcome_group_cmd.command("off")
    async def disable_welcome(self, event: AstrMessageEvent):
        """关闭当前群的入群欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["enabled"] = False
            self.save_config()
        yield event.plain_result("本群入群欢迎功能已关闭。")

    @welcome_group_cmd.command("test")
    async def test_welcome(self, event: AstrMessageEvent):
        """测试发送当前群的入群欢迎语（独立消息，无 reply）"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        group_config = self.config["groups"].get(group_id, {})
        template = group_config.get("message", self.config["default_message"])
        user_id = event.get_sender_id()
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
        message_list = self._build_onebot_message(processed, user_id)

        sent = await self._try_send_via_bot(event, group_id, message_list)
        if not sent:
            yield event.plain_result("无法发送测试消息，请检查 bot 连接或日志。")

    # ---- 退群通知指令 ----

    @welcome_group_cmd.command_group("leave")
    def leave_cmd(self):
        """退群通知管理"""
        pass

    @leave_cmd.command("set")
    async def set_leave(self, event: AstrMessageEvent, message: str):
        """设置退群通知语。支持变量: {at}, {user_id}, {time}。例如: /welcome leave set {user_id} 离开了本群"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        message = self._get_full_message(event, "set")
        if not message:
            yield event.plain_result("请提供退群通知语内容。")
            return
            
        self._ensure_group(group_id)
        self.config["groups"][group_id]["leave_enabled"] = True
        self.config["groups"][group_id]["leave_message"] = message
        self.save_config()
        yield event.plain_result(f"已设置本群退群通知语为：\n{message}")

    @leave_cmd.command("on")
    async def enable_leave(self, event: AstrMessageEvent):
        """开启当前群的退群通知"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        self._ensure_group(group_id)
        self.config["groups"][group_id]["leave_enabled"] = True
        self.save_config()
        yield event.plain_result("本群退群通知已开启。")

    @leave_cmd.command("off")
    async def disable_leave(self, event: AstrMessageEvent):
        """关闭当前群的退群通知"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["leave_enabled"] = False
            self.save_config()
        yield event.plain_result("本群退群通知已关闭。")

    @leave_cmd.command("test")
    async def test_leave(self, event: AstrMessageEvent):
        """测试发送当前群的退群通知（独立消息，无 reply）"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        group_config = self.config["groups"].get(group_id, {})
        template = group_config.get("leave_message", self.config["default_leave_message"])
        user_id = event.get_sender_id()
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
        message_list = self._build_onebot_message(processed, user_id)

        sent = await self._try_send_via_bot(event, group_id, message_list)
        if not sent:
            yield event.plain_result("无法发送测试消息，请检查 bot 连接或日志。")

    # ---- 被踢通知指令 ----

    @welcome_group_cmd.command_group("kick")
    def kick_cmd(self):
        """被踢通知管理"""
        pass

    @kick_cmd.command("set")
    async def set_kick(self, event: AstrMessageEvent, message: str):
        """设置被踢通知语。支持变量: {at}, {user_id}, {time}。例如: /welcome kick set {user_id} 被移出了本群"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        message = self._get_full_message(event, "set")
        if not message:
            yield event.plain_result("请提供被踢通知语内容。")
            return
            
        self._ensure_group(group_id)
        self.config["groups"][group_id]["kick_enabled"] = True
        self.config["groups"][group_id]["kick_message"] = message
        self.save_config()
        yield event.plain_result(f"已设置本群被踢通知语为：\n{message}")

    @kick_cmd.command("on")
    async def enable_kick(self, event: AstrMessageEvent):
        """开启当前群的被踢通知"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        self._ensure_group(group_id)
        self.config["groups"][group_id]["kick_enabled"] = True
        self.save_config()
        yield event.plain_result("本群被踢通知已开启。")

    @kick_cmd.command("off")
    async def disable_kick(self, event: AstrMessageEvent):
        """关闭当前群的被踢通知"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["kick_enabled"] = False
            self.save_config()
        yield event.plain_result("本群被踢通知已关闭。")

    @kick_cmd.command("test")
    async def test_kick(self, event: AstrMessageEvent):
        """测试发送当前群的被踢通知（独立消息，无 reply）"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("请在群聊中使用此指令。")
            return

        group_config = self.config["groups"].get(group_id, {})
        template = group_config.get("kick_message", self.config["default_kick_message"])
        user_id = event.get_sender_id()
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
        message_list = self._build_onebot_message(processed, user_id)

        sent = await self._try_send_via_bot(event, group_id, message_list)
        if not sent:
            yield event.plain_result("无法发送测试消息，请检查 bot 连接或日志。")

    # ==================== 工具方法 ====================

    @staticmethod
    def _get_raw_message(event: AstrMessageEvent):
        """兼容不同 event 类型获取 raw_message"""
        # 尝试多种方式获取原始消息
        if hasattr(event, 'raw_message'):
            return event.raw_message
        elif hasattr(event, 'message_obj') and hasattr(event.message_obj, 'raw_message'):
            return event.message_obj.raw_message
        # 尝试从 event 的 __dict__ 中获取
        elif hasattr(event, '__dict__'):
            for key in ['raw_event', 'event_data', '_raw']:
                if key in event.__dict__:
                    return event.__dict__[key]
        # 尝试使用 getattr
        for attr in ['raw_event', 'event_data', 'data']:
            if hasattr(event, attr):
                return getattr(event, attr)
        return None

    @staticmethod
    def _parse_time(raw: dict) -> str:
        """将 OneBot 事件中的 time 字段转为格式化字符串"""
        event_time = raw.get("time", time.time())
        try:
            return datetime.fromtimestamp(event_time).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_group(self, group_id: str):
        """确保群配置条目存在"""
        if group_id not in self.config["groups"]:
            self.config["groups"][group_id] = {}

    @staticmethod
    def _build_onebot_message(template: str, user_id) -> list:
        """将模板字符串转为 OneBot v11 消息段列表"""
        message_list = []
        if "{at}" in template:
            parts = template.split("{at}")
            for i, part in enumerate(parts):
                if part:
                    message_list.append({"type": "text", "data": {"text": part}})
                if i < len(parts) - 1:
                    message_list.append({"type": "at", "data": {"qq": str(user_id)}})
        else:
            message_list.append({"type": "text", "data": {"text": template}})
        return message_list

    @staticmethod
    async def _send_group_msg(event: AstrMessageEvent, group_id: str, message_list: list) -> bool:
        """通过 bot.send_group_msg 发送群消息（绕过管道，不带 reply），返回是否成功"""
        bot = getattr(event, "bot", None)
        if bot and hasattr(bot, "send_group_msg"):
            try:
                await bot.send_group_msg(group_id=int(group_id), message=message_list)
                logger.info(f"WelcomePlugin: bot.send_group_msg 发送成功 -> 群 {group_id}")
                return True
            except Exception as e:
                logger.error(f"WelcomePlugin: bot.send_group_msg 发送失败: {e}")
                return False
        else:
            logger.warning("WelcomePlugin: 无法获取 bot 对象")
            return False

    @staticmethod
    async def _try_send_via_bot(event: AstrMessageEvent, group_id: str, message_list: list) -> bool:
        """尝试通过 bot.send_group_msg 发送，成功返回 True，失败/不可用返回 False"""
        bot = getattr(event, "bot", None)
        if bot and hasattr(bot, "send_group_msg"):
            try:
                await bot.send_group_msg(group_id=int(group_id), message=message_list)
                logger.info(f"WelcomePlugin: test 发送成功 -> 群 {group_id}")
                return True
            except Exception as e:
                logger.error(f"WelcomePlugin: test 发送失败: {e}")
        else:
            logger.warning("WelcomePlugin: test 无法获取 bot 对象")
        return False

    @staticmethod
    def _build_fallback_chain(processed: str, user_id) -> list:
        """构建 AstrBot 格式的回退消息链（用于 chain_result 兜底）"""
        chain = []
        if "{at}" in processed:
            parts = processed.split("{at}")
            for i, part in enumerate(parts):
                if part:
                    chain.append(Plain(part))
                if i < len(parts) - 1:
                    chain.append(At(qq=user_id))
        else:
            chain.append(Plain(processed))
        return chain

    @staticmethod
    def _get_full_message(event: AstrMessageEvent, subcmd: str) -> str:
        """从原始消息中提取指令参数之后的内容"""
        full_text = event.message_str
        parts = full_text.split()
        # 找到 subcmd 的位置，取其后所有内容
        try:
            idx = parts.index(subcmd)
            return " ".join(parts[idx + 1:])
        except (ValueError, IndexError):
            return ""