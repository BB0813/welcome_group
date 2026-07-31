from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain
# 引入配置相关模块
from astrbot.api.config import AstrBotConfig, Option, OptionType
import json
import os
from datetime import datetime
from pathlib import Path

@register(
    "welcome_group",
    "YourName",
    "QQ群新人入群自动欢迎插件",
    "2.4.0",
    "https://github.com/mjy1113451/welcome_group"
)
class WelcomePlugin(Star):
    
    # ==================== 插件配置定义 ====================
    # 这里的配置会自动显示在 AstrBot 的 Web 配置面板中
    
    class PluginConfig(AstrBotConfig):
        # 1. 是否启用全局欢迎语（及退群通知）
        global_enabled: bool = Option(
            "启用全局模式",
            False,
            description="开启后，所有未单独配置的群将使用下方的全局消息模板"
        )
        
        # 2. 全局入群欢迎语
        global_increase_message: str = Option(
            "全局入群欢迎语",
            "欢迎 {at} 加入本群！当前时间：{time}",
            description="当新成员加群时发送。支持变量: {at}(@用户), {user_id}(QQ号), {time}(时间)",
            type=OptionType.TEXT
        )
        
        # 3. 全局退群提示
        global_leave_message: str = Option(
            "全局退群提示",
            "{user_id} 离开了本群。",
            description="当成员主动退群时发送。支持变量: {user_id}, {time}",
            type=OptionType.TEXT
        )
        
        # 4. 全局被踢提示
        global_kick_message: str = Option(
            "全局被踢提示",
            "{user_id} 被移出了本群。",
            description="当成员被管理员移出时发送。支持变量: {user_id}, {time}",
            type=OptionType.TEXT
        )

    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化数据目录路径
        try:
            from astrbot.api.star import StarTools
            self.data_dir = StarTools.get_data_dir() / "welcome_group"
        except ImportError:
            self.data_dir = Path(os.getcwd()) / "data" / "welcome_group"
        
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_path = self.data_dir / "config.json"
        
        # 初始化配置文件
        self.config = self.load_config()
        
        # 获取插件配置实例 (用于读取 Web 面板的设置)
        self.astrbot_config = self.get_config()

    def _get_default_config(self) -> dict:
        """获取默认配置结构"""
        return {
            "groups": {},
            # 用于存储插件配置，确保和 Web 面板同步
            "plugin_config": {} 
        }

    def load_config(self) -> dict:
        """加载配置文件并同步到插件配置对象"""
        default_config = self._get_default_config()
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                
                # 合并顶层配置
                for key, value in default_config.items():
                    if key not in saved:
                        saved[key] = value
                
                # ===== 关键步骤：将 JSON 中的 plugin_config 同步到 self.astrbot_config =====
                # 这样即使手动改了 JSON，Web 面板也能显示正确的值
                plugin_cfg = saved.get("plugin_config", {})
                
                # 如果 JSON 中有值，则更新内存中的配置对象
                if "global_enabled" in plugin_cfg:
                    self.astrbot_config.global_enabled = plugin_cfg["global_enabled"]
                if "global_increase_message" in plugin_cfg:
                    self.astrbot_config.global_increase_message = plugin_cfg["global_increase_message"]
                if "global_leave_message" in plugin_cfg:
                    self.astrbot_config.global_leave_message = plugin_cfg["global_leave_message"]
                if "global_kick_message" in plugin_cfg:
                    self.astrbot_config.global_kick_message = plugin_cfg["global_kick_message"]
                    
                return saved
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
                return default_config
        return default_config

    def save_config(self):
        """保存配置到文件（将 Web 配置回写 JSON）"""
        try:
            # ===== 关键步骤：将当前的 Web 配置写入 JSON =====
            # 确保在 Web 面板修改后，数据能持久化
            self.config["plugin_config"] = {
                "global_enabled": self.astrbot_config.global_enabled,
                "global_increase_message": self.astrbot_config.global_increase_message,
                "global_leave_message": self.astrbot_config.global_leave_message,
                "global_kick_message": self.astrbot_config.global_kick_message
            }
            
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    # ==================== 事件监听 ====================

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_increase(self, event: AstrMessageEvent):
        """处理新人入群事件"""
        try:
            raw = self._get_raw_message(event)
            if not raw or not isinstance(raw, dict):
                return
            
            if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_increase":
                return
            
            group_id = str(raw.get("group_id"))
            user_id = raw.get("user_id")
            self_id = raw.get("self_id")
            
            # 忽略机器人自己进群
            if str(user_id) == str(self_id):
                return
            
            group_config = self.config["groups"].get(group_id)
            welcome_template = ""
            
            if not group_config:
                # 如果群未配置，检查全局开关
                if self.astrbot_config.global_enabled:
                    logger.info(f"群 {group_id} 未配置，使用全局入群欢迎语 (配置面板设置)")
                    welcome_template = self.astrbot_config.global_increase_message
                else:
                    # 如果全局没开，则不做任何事 (或按需求可设为空)
                    logger.info(f"群 {group_id} 未配置且全局模式未开启，跳过欢迎")
                    return
            else:
                # 群已配置，检查群开关
                if not group_config.get("enabled", False):
                    return
                # 使用群独立配置，如果没填则回退到全局配置
                welcome_template = group_config.get("message", self.astrbot_config.global_increase_message)
            
            # 发送消息
            time_str = self._parse_time(raw)
            processed = welcome_template.replace("{time}", time_str).replace("{user_id}", str(user_id))
            message_list = self._build_onebot_message(processed, user_id)
            
            success = await self._send_group_msg(event, group_id, message_list)
            if not success:
                try:
                    chain = self._build_fallback_chain(processed, user_id)
                    if hasattr(event, 'send'):
                        await event.send(chain)
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"处理入群事件时出错: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_decrease(self, event: AstrMessageEvent):
        """处理退群 / 被踢出群事件"""
        try:
            raw = self._get_raw_message(event)
            if not raw or not isinstance(raw, dict):
                return
            
            if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_decrease":
                return
            
            sub_type = raw.get("sub_type", "")
            group_id = str(raw.get("group_id"))
            user_id = raw.get("user_id")
            self_id = raw.get("self_id")
            
            if sub_type == "kick_me" or str(user_id) == str(self_id):
                return
            
            group_config = self.config["groups"].get(group_id, {})
            template = ""
            
            # 默认使用插件配置中的全局模板
            default_leave = self.astrbot_config.global_leave_message
            default_kick = self.astrbot_config.global_kick_message
            
            if sub_type == "leave":
                # 退群逻辑
                if not group_config.get("leave_enabled", False):
                    # 如果群没有开启退群通知，则不发送（除非你想全局默认开启，这里假设默认关闭需手动开）
                    # 如果需要全局默认生效，可以去掉这个判断，或者把 global_enabled 算进去
                    # 这里逻辑：群配置优先，如果群没配，检查群是否开启了该功能
                    if not group_config: # 群完全没配置的情况
                         if self.astrbot_config.global_enabled:
                             template = default_leave
                         else:
                             return
                    else:
                        # 群有配置，但开关关了
                        return
                
                # 如果走到了这里，说明要发送。取群配置或回退全局
                template = group_config.get("leave_message", default_leave)
                
            elif sub_type == "kick":
                # 被踢逻辑
                if not group_config.get("kick_enabled", False):
                    if not group_config:
                         if self.astrbot_config.global_enabled:
                             template = default_kick
                         else:
                             return
                    else:
                        return
                
                template = group_config.get("kick_message", default_kick)
            else:
                return
            
            time_str = self._parse_time(raw)
            processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
            message_list = self._build_onebot_message(processed, user_id)
            
            await self._send_group_msg(event, group_id, message_list)
            
        except Exception as e:
            logger.error(f"处理退群事件时出错: {e}")

    # ==================== 指令处理 ====================
    # 移除了 global 相关的指令设置，改为在插件配置中设置
    
    @filter.command_group("welcome", "欢迎功能管理")
    def welcome(self):
        pass

    @welcome.command("set", "设置当前群欢迎语", alias={'设置欢迎'})
    async def set_welcome(self, event: AstrMessageEvent, message: str):
        """
        设置当前群的入群欢迎语
        不填内容则重置为插件配置中的全局欢迎语
        """
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("⚠️ 请在群聊中使用此指令。")
            return
        
        self._ensure_group(group_id)
        
        if message.strip():
            self.config["groups"][group_id]["message"] = message
            self.config["groups"][group_id]["enabled"] = True
            hint = "✅ 已设置本群独立欢迎语。"
        else:
            # 如果没填内容，恢复默认（即读取全局配置）
            self.config["groups"][group_id]["message"] = self.astrbot_config.global_increase_message
            self.config["groups"][group_id]["enabled"] = True
            hint = "✅ 已重置本群欢迎语为全局默认。"
            
        self.save_config()
        yield event.plain_result(hint)

    @welcome.command("on", "开启当前群欢迎", alias={'开启欢迎'})
    async def enable_welcome(self, event: AstrMessageEvent):
        """开启当前群的入群欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("⚠️ 请在群聊中使用此指令。")
            return
        
        self._ensure_group(group_id)
        self.config["groups"][group_id]["enabled"] = True
        self.save_config()
        yield event.plain_result("✅ 本群入群欢迎功能已开启。")

    @welcome.command("off", "关闭当前群欢迎", alias={'关闭欢迎'})
    async def disable_welcome(self, event: AstrMessageEvent):
        """关闭当前群的入群欢迎功能"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("⚠️ 请在群聊中使用此指令。")
            return
        
        if group_id in self.config["groups"]:
            self.config["groups"][group_id]["enabled"] = False
            self.save_config()
        yield event.plain_result("✅ 本群入群欢迎功能已关闭。")

    @welcome.command("test", "测试欢迎语", alias={'测试欢迎'})
    async def test_welcome(self, event: AstrMessageEvent):
        """测试发送当前群的入群欢迎语"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("⚠️ 请在群聊中使用此指令。")
            return
        
        group_config = self.config["groups"].get(group_id, {})
        # 优先取群配置，否则取全局配置
        template = group_config.get("message", self.astrbot_config.global_increase_message)
        
        user_id = event.get_sender_id()
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        processed = template.replace("{time}", time_str).replace("{user_id}", str(user_id))
        message_list = self._build_onebot_message(processed, user_id)
        
        sent = await self._try_send_via_bot(event, group_id, message_list)
        if not sent:
            yield event.plain_result("❌ 无法发送测试消息，请检查 bot 连接或日志。")
        else:
            yield event.plain_result("✅ 测试消息已发送。")

    @welcome.command("status", "查看状态", alias={'状态'})
    async def status(self, event: AstrMessageEvent):
        """查看当前群和全局的欢迎功能状态"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("⚠️ 请在群聊中使用此指令。")
            return
        
        group_config = self.config["groups"].get(group_id, {})
        global_status = "✅ 已开启" if self.astrbot_config.global_enabled else "❌ 未开启"
        group_status = "✅ 已开启" if group_config.get("enabled", False) else "❌ 未开启"
        
        msg = (
            f"📊 欢迎功能状态:\n\n"
            f"全局模式: {global_status}\n"
            f"当前群: {group_status}\n\n"
        )
        
        if group_config.get("enabled", False):
            msg += f"当前群欢迎语:\n{group_config.get('message', '未设置(使用全局)')}\n\n"
        
        msg += f"全局默认欢迎语:\n{self.astrbot_config.global_increase_message}"
        yield event.plain_result(msg)

    # ==================== 辅助方法 ====================

    def _ensure_group(self, group_id: str):
        """确保群配置存在"""
        if group_id not in self.config["groups"]:
            self.config["groups"][group_id] = {
                "enabled": False,
                "message": "", # 留空则使用全局
                "leave_enabled": False,
                "leave_message": "",
                "kick_enabled": False,
                "kick_message": ""
            }

    def _get_raw_message(self, event: AstrMessageEvent):
        """获取原始消息数据"""
        try:
            if hasattr(event, 'get_raw_message'):
                return event.get_raw_message()
            elif hasattr(event, 'raw_message'):
                return event.raw_message
            return None
        except:
            return None

    def _parse_time(self, raw: dict) -> str:
        """解析时间"""
        try:
            timestamp = raw.get("time")
            if timestamp:
                return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _build_onebot_message(self, text: str, user_id: int) -> list:
        """构建OneBot消息链"""
        message = []
        if "{at}" in text:
            text = text.replace("{at}", f"@{user_id}")
        message.append(Plain(text))
        return message

    def _build_fallback_chain(self, text: str, user_id: int):
        """构建备用消息链（用于event.send/reply）"""
        clean_text = text.replace("{at}", "").replace(f"@{user_id}", "")
        return [Plain(clean_text)]

    async def _send_group_msg(self, event: AstrMessageEvent, group_id: str, message: list) -> bool:
        """尝试发送群消息（直接调用API）"""
        try:
            if hasattr(event, 'call_api'):
                await event.call_api("send_group_msg", group_id=int(group_id), message=message)
                return True
            return False
        except Exception as e:
            logger.error(f"调用send_group_msg失败: {e}")
            return False

    async def _try_send_via_bot(self, event: AstrMessageEvent, group_id: str, message: list) -> bool:
        """尝试通过bot对象发送消息"""
        try:
            if hasattr(event, 'bot') and hasattr(event.bot, 'call_api'):
                await event.bot.call_api("send_group_msg", group_id=int(group_id), message=message)
                return True
            return False
        except Exception as e:
            logger.error(f"通过bot发送消息失败: {e}")
            return False
