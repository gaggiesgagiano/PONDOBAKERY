// PondoFiscalBridge - lets Pondo (Python) talk to the FiscalStackZW engine (.NET Framework 4.8 DLL).
//
// One process = one engine instance (the engine wants exactly one, with calls one after the other).
// Pondo starts this program once, then sends one JSON request per line on standard input:
//     {"id": 7, "method": "TransactM", "args": ["USD", "", "T1-00012", ...]}
// and reads one JSON reply per line on standard output:
//     {"id": 7, "ok": true, "result": "<the engine's envelope string>"}
//     {"id": 7, "ok": false, "error": "what went wrong"}
// Anything the engine itself prints (its console log) is sent to standard error, never into the replies.
//
// Written for the C# 5 compiler that comes with every Windows (.NET Framework 4.x csc.exe),
// so it can be rebuilt on the bakery computer with build_bridge.bat - no Visual Studio needed.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PondoFiscal
{
    internal static class Program
    {
        private static StreamWriter reply;

        private static int Main(string[] argv)
        {
            UTF8Encoding utf8 = new UTF8Encoding(false);
            reply = new StreamWriter(Console.OpenStandardOutput(), utf8);
            reply.AutoFlush = true;
            StreamReader input = new StreamReader(Console.OpenStandardInput(), utf8);
            Console.SetOut(Console.Error);   // the engine's own console output goes to the log file

            try { Directory.SetCurrentDirectory(AppDomain.CurrentDomain.BaseDirectory); }
            catch (Exception) { }

            object engine = null;
            string startError = null;
            try { engine = new FiscalStackZW.FiscalStackZW(); }
            catch (Exception ex) { startError = Flatten(ex); }

            JObject hello = Info(engine, startError);
            hello["id"] = 0;
            hello["ok"] = startError == null;
            hello["ready"] = true;
            Send(hello);

            string line;
            while ((line = input.ReadLine()) != null)
            {
                line = line.Trim();
                if (line.Length == 0) continue;
                JToken id = JValue.CreateNull();
                try
                {
                    JObject req = JObject.Parse(line);
                    if (req["id"] != null) id = req["id"];
                    string method = (string)req["method"] ?? "";
                    JArray args = req["args"] as JArray ?? new JArray();

                    if (method == "__exit") { SendOk(id, "bye"); break; }
                    if (method == "__info") { JObject i = Info(engine, startError); i["id"] = id; i["ok"] = true; Send(i); continue; }
                    if (engine == null) { SendError(id, "The fiscal engine could not start: " + startError); continue; }
                    if (method == "__zimra") { JObject z = CallZimra(engine, args); z["id"] = id; z["ok"] = true; Send(z); continue; }

                    object result = Invoke(engine, method, args);
                    SendOk(id, result == null ? "" : Convert.ToString(result, CultureInfo.InvariantCulture));
                }
                catch (Exception ex)
                {
                    SendError(id, Flatten(ex));
                }
            }
            return 0;
        }

        private static JObject Info(object engine, string startError)
        {
            JObject o = new JObject();
            o["bridge"] = "PondoFiscalBridge 1.1";
            o["startError"] = startError;
            o["engineVersion"] = typeof(FiscalStackZW.FiscalStackZW).Assembly.GetName().Version.ToString();
            o["is64bit"] = Environment.Is64BitProcess;
            if (engine != null)
            {
                o["isInitialized"] = JToken.FromObject(ReadProp(engine, "IsInitialized") ?? false);
                object err = ReadProp(engine, "InitializationError");
                o["initializationError"] = err == null ? null : err.ToString();
            }
            return o;
        }

        // Ask ZIMRA directly through the engine's own gateway (same certificate and server), e.g. ["GetStatus"].
        // Read-only use: Pondo calls GetStatus / GetConfig to reconcile its counters with ZIMRA.
        private static JObject CallZimra(object engine, JArray args)
        {
            string name = args.Count > 0 ? (string)args[0] : "GetStatus";
            if (name != "GetStatus" && name != "GetConfig" && name != "Ping")
                throw new InvalidOperationException("Only GetStatus, GetConfig and Ping can be asked directly.");
            PropertyInfo zp = engine.GetType().GetProperty("Zimra", BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance);
            if (zp == null) throw new InvalidOperationException("This engine version has no ZIMRA gateway.");
            object gw = zp.GetValue(engine, null);
            if (gw == null) throw new InvalidOperationException("The ZIMRA gateway is not ready (certificate missing?).");
            MethodInfo m = gw.GetType().GetMethod(name, BindingFlags.Public | BindingFlags.Instance, null, Type.EmptyTypes, null);
            if (m == null) throw new InvalidOperationException("The ZIMRA gateway has no " + name + "().");
            object r;
            try { r = m.Invoke(gw, null); }
            catch (TargetInvocationException tie) { throw tie.InnerException ?? tie; }
            JObject o = new JObject();
            o["result"] = "";
            if (r == null) return o;
            PropertyInfo t = r.GetType().GetProperty("Result");
            if (t != null && r is System.Threading.Tasks.Task) r = t.GetValue(r, null);
            foreach (string p in new string[] { "Success", "HttpStatus", "Code", "ErrorCode", "Message", "Raw" })
            {
                object v = ReadProp(r, p);
                o[p] = v == null ? null : JToken.FromObject(v.ToString());
            }
            object js = ReadProp(r, "Json");
            o["Json"] = js as JToken;
            return o;
        }

        private static object ReadProp(object target, string name)
        {
            try
            {
                PropertyInfo p = target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
                return p == null ? null : p.GetValue(target, null);
            }
            catch (Exception) { return null; }
        }

        // Find the public engine method with this name that fits the number of arguments, and call it.
        private static object Invoke(object engine, string method, JArray args)
        {
            MethodInfo best = null;
            foreach (MethodInfo m in engine.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance))
            {
                if (m.Name != method || m.IsSpecialName) continue;
                ParameterInfo[] ps = m.GetParameters();
                if (args.Count > ps.Length) continue;
                bool fits = true;
                for (int i = args.Count; i < ps.Length; i++)
                    if (!ps[i].IsOptional) { fits = false; break; }
                if (!fits) continue;
                if (best == null || ps.Length < best.GetParameters().Length) best = m;
            }
            if (best == null)
                throw new InvalidOperationException("The engine has no method " + method + " taking " + args.Count + " argument(s).");

            ParameterInfo[] pars = best.GetParameters();
            object[] values = new object[pars.Length];
            for (int i = 0; i < pars.Length; i++)
                values[i] = i < args.Count ? ToType(args[i], pars[i].ParameterType) : pars[i].DefaultValue;
            try
            {
                return best.Invoke(engine, values);
            }
            catch (TargetInvocationException tie)
            {
                throw tie.InnerException ?? tie;
            }
        }

        private static object ToType(JToken t, Type type)
        {
            if (t == null || t.Type == JTokenType.Null)
                return type.IsValueType ? Activator.CreateInstance(type) : null;
            if (type == typeof(string))
                return t.Type == JTokenType.String ? (string)t : t.ToString(Formatting.None);
            string s = t.Type == JTokenType.String ? (string)t : t.ToString(Formatting.None);
            if (type == typeof(int)) return int.Parse(s, CultureInfo.InvariantCulture);
            if (type == typeof(long)) return long.Parse(s, CultureInfo.InvariantCulture);
            if (type == typeof(decimal)) return decimal.Parse(s, CultureInfo.InvariantCulture);
            if (type == typeof(double)) return double.Parse(s, CultureInfo.InvariantCulture);
            if (type == typeof(bool)) return s == "1" || s.Equals("true", StringComparison.OrdinalIgnoreCase);
            return Convert.ChangeType(s, type, CultureInfo.InvariantCulture);
        }

        private static string Flatten(Exception ex)
        {
            StringBuilder sb = new StringBuilder();
            List<string> seen = new List<string>();
            for (Exception e = ex; e != null; e = e.InnerException)
            {
                string m = e.GetType().Name + ": " + e.Message;
                if (seen.Contains(m)) continue;
                seen.Add(m);
                if (sb.Length > 0) sb.Append(" -> ");
                sb.Append(m);
            }
            return sb.ToString();
        }

        private static void SendOk(JToken id, string result)
        {
            JObject o = new JObject();
            o["id"] = id;
            o["ok"] = true;
            o["result"] = result;
            Send(o);
        }

        private static void SendError(JToken id, string error)
        {
            JObject o = new JObject();
            o["id"] = id;
            o["ok"] = false;
            o["error"] = error;
            Send(o);
        }

        private static void Send(JObject o)
        {
            reply.WriteLine(o.ToString(Formatting.None));   // one line per reply; newlines inside strings are escaped
        }
    }
}
