# Jinkra Virtual Mic

这是 Jinkra 自带的 Windows x64 WaveRT 驱动工程。录音端是 **Jinkra Virtual Mic**，
播放端是 **Jinkra Mix Input**，设备管理器里的适配器是 **Jinkra Virtual Audio**。
硬件 ID 为 `ROOT\JINKRAVAD`，最低支持 Windows 10 2004（19041）x64。
应用把选中的实体麦克风和音效在用户态混音，
通过 WASAPI 共享模式写入播放端。驱动用非分页环形缓冲将 PCM 提供给录音端。

驱动及原生安装辅助工具改造自 MicDeck VAD 的
[4ec7e53](https://github.com/3godzinyL/Virtual-Soundboard-Audio-Windows-Mixer/tree/4ec7e53c0ac37291187d92f3d75bf88af469895c/drivers/micdeck-vad)。
保留原有 MIT 许可。Jinkra 使用独立的硬件 ID、服务名、接口名称与属性集 GUID。

## 构建和发布

1. 在 Visual Studio 2022 Developer PowerShell 中安装并启用配套的 Windows Driver Kit 与 C++ 工具链，运行 `./build.ps1`。构建的驱动文件为 `JinkraVad.sys`，包描述为 `package/JinkraVad.inf`。
2. 使用 `package-driver.ps1` 和 WDK 的 `InfVerif.exe`、`Inf2Cat.exe` 验证 INF 及文件，并把 `.inf`、`.sys`、`.cat` 和匹配的 `.pdb` 打成待签名 CAB。将驱动通过 Microsoft Hardware Dev Center 正式签名。取得签名件后，用 `signtool verify /kp /c JinkraVad.cat JinkraVad.sys` 和 `signtool verify /kp /c JinkraVad.cat JinkraVad.inf` 验证签名与文件对应关系。
3. 将签名后的 `JinkraVad.inf`、`JinkraVad.sys` 和 `JinkraVad.cat` 放在应用旁的 `VirtualMic` 目录，也可以从软件中选择包含这些文件的目录。点击「安装虚拟麦克风」后，Windows 会请求管理员确认，辅助程序会注册根设备并调用驱动安装接口。安装完成后，普通权限即可使用录音设备。
4. 在保持设备正常安全配置的 Windows 10/11 上验证两个端点、声音跨端点传输、拔插实体麦克风、重启，以及 Discord 或目标游戏录音。

当前便携包包含安装辅助程序。待签名 CAB 与安装目录独立存放，正式发布前须完成 Microsoft 签名与系统录音验证。

[微软驱动代码签名要求](https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/code-signing-reqs) ·
[微软签名提交步骤](https://learn.microsoft.com/windows-hardware/drivers/dashboard/code-signing-attestation)
