// Jinkra Voiceover Roulette 的系统语音助手：把文字用 Windows 自带语音合成为 WAV。
//   jinkra-tts list                          每行：语音ID \t 名称 \t 语言 \t 性别
//   jinkra-tts speak <语音ID> <语速> <输出.wav>   朗读文字从标准输入读取（UTF-8），语速 0.5~3.0
//
// 两类语音：
//   winrt:<ID>  Windows 10/11 的 OneCore 语音（慧慧、康康、瑶瑶……），走 Windows.Media.SpeechSynthesis。
//               老的 SAPI 接口用这些语音时选不中音色，会悄悄退回默认语音，所以必须走这条路。
//   sapi:<ID>   只有桌面 SAPI 才有的语音（例如英文 Zira Desktop）。
// 用 .NET Framework 4.x 自带的 csc（C# 5）编译，SAPI 部分通过 COM 反射调用。
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using Windows.Foundation;
using Windows.Media.SpeechSynthesis;
using Windows.Storage.Streams;

internal static class JinkraTts
{
    private const string SapiVoices = @"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices";

    // ---------------------------------------------------------------- 列出语音

    private static int List()
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var output = new StringBuilder();
        try
        {
            foreach (VoiceInformation voice in SpeechSynthesizer.AllVoices)
            {
                seen.Add(Short(voice.DisplayName));
                output.Append("winrt:").Append(voice.Id).Append('\t').Append(voice.DisplayName).Append('\t')
                      .Append(voice.Language).Append('\t').Append(voice.Gender == VoiceGender.Male ? "Male" : "Female")
                      .Append('\n');
            }
        }
        catch (Exception) { }  // 精简版系统可能没有 OneCore 语音
        try
        {
            object tokens = Call(SapiCategory(), "EnumerateTokens", "", "");
            int count = (int)Get(tokens, "Count");
            for (int i = 0; i < count; i++)
            {
                object token = Call(tokens, "Item", i);
                string name = Attribute(token, "Name");
                // 同一个语音（例如慧慧）两边都有时只留 OneCore 那份
                if (name.Length == 0 || seen.Contains(Short(name))) continue;
                output.Append("sapi:").Append((string)Get(token, "Id")).Append('\t').Append(name).Append('\t')
                      .Append(Lcid(Attribute(token, "Language"))).Append('\t').Append(Attribute(token, "Gender"))
                      .Append('\n');
            }
        }
        catch (Exception) { }
        Write(Console.OpenStandardOutput(), output.ToString());
        return 0;
    }

    // "Microsoft Huihui Desktop" / "Microsoft Huihui" -> "huihui"
    private static string Short(string name)
    {
        string[] parts = name.Split(' ');
        return (parts.Length > 1 ? parts[1] : name).ToLowerInvariant();
    }

    private static string Lcid(string hex)
    {
        try
        {
            string first = hex.Split(';')[0];
            return new System.Globalization.CultureInfo(Convert.ToInt32(first, 16)).Name;
        }
        catch (Exception) { return hex; }
    }

    // ---------------------------------------------------------------- 合成

    private static int Speak(string id, double rate, string path)
    {
        string text;
        using (var input = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false)))
            text = input.ReadToEnd();
        if (text.Trim().Length == 0) return 3;
        rate = Math.Max(0.5, Math.Min(3.0, rate));
        if (id.StartsWith("winrt:", StringComparison.Ordinal)) SpeakWinRt(id.Substring(6), rate, text, path);
        else if (id.StartsWith("sapi:", StringComparison.Ordinal)) SpeakSapi(id.Substring(5), rate, text, path);
        else throw new ArgumentException("未知的语音：" + id);
        return 0;
    }

    private static void SpeakWinRt(string id, double rate, string text, string path)
    {
        VoiceInformation chosen = null;
        foreach (VoiceInformation voice in SpeechSynthesizer.AllVoices)
            if (voice.Id == id) chosen = voice;
        if (chosen == null) throw new ArgumentException("找不到这个系统语音，可能已被卸载。");
        using (var synth = new SpeechSynthesizer())
        {
            synth.Voice = chosen;
            synth.Options.SpeakingRate = rate;
            // 不用 AsTask()/AsStreamForRead()：它们需要 Windows SDK 才有的合并元数据，
            // 这里直接轮询异步操作，再用 DataReader 读出整段（已含 WAV 文件头）。
            IAsyncOperation<SpeechSynthesisStream> synthesis = synth.SynthesizeTextToStreamAsync(text);
            Wait(synthesis);
            using (SpeechSynthesisStream stream = synthesis.GetResults())
            {
                uint size = (uint)stream.Size;
                using (var reader = new DataReader(stream.GetInputStreamAt(0)))
                {
                    IAsyncOperation<uint> load = reader.LoadAsync(size);
                    Wait(load);
                    var bytes = new byte[load.GetResults()];
                    reader.ReadBytes(bytes);
                    File.WriteAllBytes(path, bytes);
                }
            }
        }
    }

    private static void Wait(IAsyncInfo operation)
    {
        var deadline = DateTime.UtcNow.AddMinutes(2);
        while (operation.Status == AsyncStatus.Started)
        {
            if (DateTime.UtcNow > deadline) throw new TimeoutException("系统语音合成超时。");
            System.Threading.Thread.Sleep(10);
        }
        if (operation.Status != AsyncStatus.Completed)
            throw operation.ErrorCode ?? new InvalidOperationException("系统语音合成失败。");
    }

    private static void SpeakSapi(string tokenId, double rate, string text, string path)
    {
        object voice = Create("SAPI.SpVoice");
        object token = null;
        object tokens = Call(SapiCategory(), "EnumerateTokens", "", "");
        int count = (int)Get(tokens, "Count");
        for (int i = 0; i < count; i++)
        {
            object item = Call(tokens, "Item", i);
            if (String.Equals((string)Get(item, "Id"), tokenId, StringComparison.OrdinalIgnoreCase)) token = item;
        }
        if (token == null) throw new ArgumentException("找不到这个系统语音，可能已被卸载。");
        Set(voice, "Voice", token);
        // SAPI 语速 -10~10，约每 +1 快 10%：把倍率换算过去
        Set(voice, "Rate", (int)Math.Round(Math.Max(-10, Math.Min(10, Math.Log(rate) / Math.Log(1.1)))));
        object format = Create("SAPI.SpAudioFormat");
        Set(format, "Type", 22);                 // SAFT22kHz16BitMono
        object stream = Create("SAPI.SpFileStream");
        Set(stream, "Format", format);
        Call(stream, "Open", path, 3, false);    // SSFMCreateForWrite
        try
        {
            Set(voice, "AudioOutputStream", stream);
            Call(voice, "Speak", text, 0);       // 同步：写完才返回
        }
        finally { Call(stream, "Close"); }
    }

    // ---------------------------------------------------------------- COM 反射小工具

    private static object SapiCategory()
    {
        object category = Create("SAPI.SpObjectTokenCategory");
        Call(category, "SetId", SapiVoices, false);
        return category;
    }

    private static object Create(string progId)
    {
        return Activator.CreateInstance(Type.GetTypeFromProgID(progId, true));
    }

    private static object Call(object target, string name, params object[] args)
    {
        return target.GetType().InvokeMember(name, BindingFlags.InvokeMethod, null, target, args);
    }

    private static object Get(object target, string name)
    {
        return target.GetType().InvokeMember(name, BindingFlags.GetProperty, null, target, null);
    }

    private static void Set(object target, string name, object value)
    {
        target.GetType().InvokeMember(name, BindingFlags.SetProperty, null, target, new[] { value });
    }

    private static string Attribute(object token, string name)
    {
        try { return (Call(token, "GetAttribute", name) as string) ?? ""; }
        catch (Exception) { return ""; }
    }

    private static void Write(Stream stream, string text)
    {
        byte[] bytes = new UTF8Encoding(false).GetBytes(text);
        using (stream) stream.Write(bytes, 0, bytes.Length);
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "list") return List();
            if (args.Length == 4 && args[0] == "speak")
                return Speak(args[1], double.Parse(args[2], System.Globalization.CultureInfo.InvariantCulture), args[3]);
            Write(Console.OpenStandardError(), "usage: jinkra-tts list | speak <voice> <rate> <out.wav>");
            return 2;
        }
        catch (Exception error)
        {
            while ((error is TargetInvocationException || error is AggregateException) && error.InnerException != null)
                error = error.InnerException;
            Write(Console.OpenStandardError(), error.Message);
            return 1;
        }
    }
}
