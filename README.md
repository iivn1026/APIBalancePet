# APIBalancePet

一个轻量的 Windows API 余额桌宠。平时只显示透明角色，点击角色后，在头顶弹出云朵形思考气泡，查看余额和模型用量。

<img src="avatar.png" alt="APIBalancePet 默认角色" width="140">

## 功能

- **云朵余额气泡**：展示钱包余额、Key 剩余额度或订阅额度；靠近屏幕边缘时调整位置。
- **模型用量**：显示当前 Key 的模型名称、Token 数和实际花费，多个模型可翻页。
- **自定义外观**：导入 PNG、JPG、WebP，保留透明背景，支持 30%～200% 实时缩放。
- **自定义连接**：请求地址与余额接口路径分开设置，路径默认 `/v1/usage`。
- **自动刷新**：默认每 300 秒刷新，可设置 60～86400 秒；低余额时改变金额颜色。
- **本机配置**：API Key 使用 Windows DPAPI 加密保存，角色图片仅复制到本机。

程序不预设服务商地址，也不包含 API Key、账号或个人配置。首次启动可先体验桌宠，再通过右键设置连接信息。

## 直接运行

环境：Windows 10 / 11，64 位。打包版不需要安装 Python。

下载：[最新 Windows 版本](https://github.com/iivn1026/APIBalancePet/releases/latest)。可以下载单独 EXE，也可以解压包含程序、README 和 MIT 许可证的便携包。

1. 打开下载的 `APIBalancePet.exe`；本地源码交付文件夹中的程序位于 `dist/APIBalancePet.exe`。
2. 右键角色，选择 **设置 → 接口连接**。
3. 填写请求地址，例如 `https://example.com`，再填写自己的 API Key。
4. 按站点文档填写余额接口路径；留空时使用 `/v1/usage`。
5. 保存，左键点击角色查看结果。

地址中的路径部分不会与接口路径叠加：`https://example.com` 加 `/api/balance`，最终请求 `https://example.com/api/balance`。

### 操作

| 操作 | 效果 |
| --- | --- |
| 左键单击角色 | 打开或收起云朵气泡，并在已配置连接时刷新 |
| 按住左键拖动 | 移动角色，收起气泡 |
| 右键角色 | 刷新余额、设置、退出 |
| 点击气泡外部、点击 × 或按 Esc | 收起气泡 |
| 气泡内箭头或鼠标滚轮 | 翻阅模型用量 |

### 图片与大小

设置中的 **图片与大小** 标签页支持导入、恢复默认图片和实时缩放。点击保存保留修改，点击取消或关闭设置窗口恢复原样。外观可独立保存，不必先填写 API Key。

导入图片会在本机保存独立副本，因此移动原图不会影响桌宠。透明 PNG / WebP 保留透明背景；普通 JPG 保留原背景，不会自动抠图。动图仅显示第一帧。Windows 色键透明采用二值边缘，半透明部分不会完整保留。

## 接口兼容性

本项目支持兼容下述 JSON 结构的余额接口，**不是任意服务商都通用**。能调用模型的 API Key，不一定有余额或模型统计查询权限。更换接口路径不会自动适配不同的认证方式或响应结构。

请求方式：

```http
GET /v1/usage
Authorization: Bearer <在本机填写的 API Key>
Accept: application/json
```

启用用量显示时，会附加 `start_date`、`end_date` 和 `days` 参数。关闭后，仅查询配置的余额路径，不附加这些统计参数。请求仅允许 HTTPS，超时为 20 秒，不跟随重定向。

兼容响应示例（全部为模拟数据）：

```json
{
  "isValid": true,
  "mode": "unrestricted",
  "balance": 12.34,
  "unit": "USD",
  "model_stats": [
    {
      "model": "example-model",
      "total_tokens": 1024,
      "actual_cost": 0.001
    }
  ]
}
```

也支持把上述内容包在顶层 `data` 对象中。

| 字段 | 显示逻辑 |
| --- | --- |
| `balance` | 钱包余额，优先显示；可以为 0 |
| `mode: quota_limited` + `remaining` 或 `quota.remaining` | Key 剩余额度，不等于账户钱包 |
| `remaining` + 订阅信息 | 订阅剩余额度；订阅的 `-1` 显示为不限额 |
| `model_stats[].model` / `model_name` | 模型名称 |
| `model_stats[].total_tokens` | Token 总量；缺失显示“未提供” |
| `model_stats[].actual_cost` | 实际花费，按兼容接口约定显示 USD；缺失显示“未提供” |

不会把 `cost` / `total_cost` 标价字段当成实际扣费，也不会把缺失值伪装成零。接口不返回模型统计时，余额仍可正常显示。

### 用量时间范围的限制

设置里可以关闭用量明细，或选择近 24 小时、7 天、30 天。

当前支持的接口按日期返回模型汇总，不能据此确定最后一笔请求的模型、精确请求时间或逐笔花费：

- **近 24 小时**：以今日汇总展示，气泡明确注明“非滚动 24 小时”。
- **近 7 天 / 30 天**：包含今天的 7 / 30 个自然日，并显示实际起止日期。
- 日期按本机日期生成，服务端如何解释日界取决于站点；站点时区不同可能造成边界差异。
- 模型行保留接口返回顺序，不表示最近调用顺序。服务端若忽略筛选参数，客户端无法保证其统计范围正确。

## 本机数据与隐私

独立版使用以下目录，与其他桌宠版本的配置分开：

```text
%LOCALAPPDATA%\APIBalancePet\settings.json
%LOCALAPPDATA%\APIBalancePet\images\
```

- 默认请求地址、API Key、自定义图片路径均为空，不读取旧版 `BalancePet` 的配置。
- Key 用 Windows DPAPI 加密，其他设置为普通 JSON；图片副本留在本机。
- 不上传图片，不调用聊天或生图模型，不添加开机启动，不发送遥测。
- 开启余额查询时，仅向用户配置的地址发送 Key。请自行确认填写的站点地址。
- DPAPI 保护静态文件，无法阻止已经控制当前 Windows 用户的程序读取。
- 删除 `settings.json` 可重置配置；删除 `images` 目录可清理导入图片。程序关闭后可直接删除本文件夹。

仓库应只包含源码、默认素材、文档与测试，不应提交本机配置、Key 或导入图片。

## 源码运行

建议在 Windows 使用 Python 3.11 或更高版本；随附程序使用 Python 3.14 构建。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe balance_pet.py
```

预览模式使用明确标注的模拟数据，不读取本机配置，也不发起余额请求：

```powershell
.venv\Scripts\python.exe balance_pet.py --preview
```

## 自行打包

在 Windows 中进入项目目录运行：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe build.py
```

生成文件：

```text
dist/APIBalancePet.exe
dist/SHA256SUMS.txt
```

`build.py` 不包含固定的开发者路径。默认素材打包进 EXE，可单独复制 EXE 使用。SHA-256 清单可以用于核对文件是否变化；程序未做代码签名。

`dist/` 已在 `.gitignore` 中忽略。发布时可把 EXE 和校验文件附在 GitHub Release 中，源码仓库保持轻量。

## 测试

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe balance_pet.py --preview --smoke-test
```

测试使用保留示例域名和模拟响应，覆盖余额解析、实际费用字段、日期范围、路径校验、图片导入及 Windows 加密读写，不需要真实 API Key。加密测试需要 Windows。图形冒烟测试启动后自动退出。

## 文件结构

```text
APIBalancePet/
├── balance_pet.py          # 查询、配置、设置页、桌宠逻辑
├── thought_bubble.py       # 云朵气泡与用量翻页
├── avatar.png             # 默认透明角色图
├── pet.ico                # 默认程序图标
├── build.py               # Windows 打包脚本
├── requirements.txt
├── requirements-build.txt
├── tests/                 # 不使用真实账号的测试
├── dist/                  # 本地打包程序和 SHA-256
└── README.md
```

## 许可证

项目源码采用 [MIT License](LICENSE)，允许使用、修改和分发，需保留版权声明与许可文本。

默认角色图片作为展示素材保留，不声明该角色为本项目原创；MIT 许可不授予第三方角色图片及其衍生图标的权利。
