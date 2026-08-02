# welcome_group

 AstrBot 入群欢迎插件 —— 自动在群聊中发送入群、离群、退群提醒消息。

## 功能特性

| 消息类型 | 说明 |
|---|---|
| **入群欢迎** | 新成员加入群聊时，自动发送自定义欢迎消息 |
| **离群通知** | 成员主动退出群聊时，发送通知 |
| **退群通知** | 成员被管理员移出群聊时，发送通知 |

### 模板变量

消息模板支持以下变量，占位符会在实际发送时被替换：

| 变量 | 说明 |
|---|---|
| `{at}` | @提及新成员 |
| `{time}` | 事件发生时间 |
| `{user_id}` | 成员的 QQ 号 |

### 群组独立配置

每个群组可以独立设置是否启用、消息模板，互不干扰。

---

## 命令

所有命令以 `/welcome` 开头，在群聊中发送即可。

### 入群欢迎

| 命令 | 说明 |
|---|---|
| `/welcome on` | 开启当前群的入群欢迎 |
| `/welcome off` | 关闭当前群的入群欢迎 |
| `/welcome set <消息>` | 设置入群欢迎消息模板 |
| `/welcome test` | 测试当前配置（不触发事件） |

### 离群通知

| 命令 | 说明 |
|---|---|
| `/welcome leave on` | 开启离群通知 |
| `/welcome leave off` | 关闭离群通知 |
| `/welcome leave set <消息>` | 设置离群消息模板 |
| `/welcome leave test` | 测试当前配置 |

### 退群通知（被踢）

| 命令 | 说明 |
|---|---|
| `/welcome kick on` | 开启退群通知 |
| `/welcome kick off` | 关闭退群通知 |
| `/welcome kick set <消息>` | 设置退群消息模板 |
| `/welcome kick test` | 测试当前配置 |

---

## 安装

本插件适用于 [AstrBot](https://github.com/Soulter/helloworld)。

将本仓库克隆到 AstrBot 的插件目录即可：

```bash
cd <你的AstrBot插件目录>
git clone https://github.com/mjy1113451/welcome_group.git
```

---

## 配置

插件首次运行后会在数据目录生成 `welcome_group/config.json`，默认配置如下：

```json
{
  "default_message": "欢迎 {at} 加入本群！当前时间：{time}",
  "default_leave_message": "{user_id} 离开了本群。",
  "default_kick_message": "{user_id} 被移出了本群。",
  "groups": {}
}
```

`groups` 字段中每个群组可独立配置，例如：

```json
{
  "groups": {
    "123456789": {
      "enabled": true,
      "message": "欢迎 {at} 来到交流群！",
      "leave_enabled": false,
      "leave_message": "",
      "kick_enabled": true,
      "kick_message": "{user_id} 被管理员移出了本群。"
    }
  }
}
```

---

## 项目结构

```
welcome_group/
├── main.py          # 插件主逻辑
├── metadata.yaml    # 插件元信息（AstrBot 加载所需）
├── README.md        # 本文档
├── LICENSE          # AGPLv3 开源协议
└── .gitignore
```

---

## 依赖

- **Python 3.10+**
- **AstrBot** 平台（运行时由 AstrBot 提供）

---

## 开源协议

本项目基于 [GNU Affero General Public License v3](https://www.gnu.org/licenses/agpl-3.0.html) 开源。
