using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using HarmonyLib;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace SFSProbe
{
    // v0.12 - fixes from the full DLL schema walk:
    //   - location.position / location.velocity are TRUE world-frame, double-
    //     precision Double2 vectors. rb2d.linearVelocityX/Y (used through v0.11)
    //     are LOCAL/rocket-frame and were never valid for a world-frame speed
    //     check -- this replaces them, closing the tangential-velocity gap.
    //   - resources.localGroups (ResourceModule[]) exposes fuel per group/tank
    //     directly: resourcePercent + wetMass, both wrapped Double_Reference.
    //   - staging.stages exposes the live stage->part mapping (Stage.stageId,
    //     Stage.parts), so fuel-by-stage no longer needs inference.
    // No live "dragArea" field exists anywhere in the schema (confirmed by
    // exhaustive search) -- it's computed inline and never stored, so the
    // empirical fit from telemetry remains the only route to that number.
    public class ProbeMod : ModLoader.Mod
    {
        // Single source of truth for the mod's own version -- was previously
        // duplicated as a literal string in both ModVersion and the load-time
        // Log() message, a real (if harmless) inconsistency risk. Now also
        // exposed live via the 'ping' command so sfsprobe_status can report
        // it without a separate round trip.
        public const string VersionString = "0.63.0";

        public override string ModNameID => "sfs_probe";
        public override string DisplayName => "SFS Probe (remote)";
        public override string Author => "christian";
        public override string MinimumGameVersionNecessary => "1.6.00.00";
        public override string ModVersion => VersionString;
        public override string Description => "Remote-controlled data probe. Poll command.txt.";

        public static string OutDir;

        public override void Load()
        {
            // Must happen BEFORE any Harmony/MonoMod type is touched --
            // MonoMod.Utils.DynamicMethodDefinition reads this env var at
            // static-init time. Kept from the v0.25.x diagnostics even
            // though this build no longer uses the game's own 0Harmony.dll
            // -- harmless either way, cheap insurance.
            try { Environment.SetEnvironmentVariable("MONOMOD_DMDType", "Cecil"); }
            catch (Exception e) { Debug.Log("[SFSProbe] couldn't set MONOMOD_DMDType: " + e.Message); }

            OutDir = ModFolder;
            Log("=== v" + VersionString + " loaded (telemetry archive lifecycle unified: flat ('truth'+'inputs' merged into one file/tag 'flat') and json ('rocketstate' renamed 'parts') modes now share one naming scheme telemetry_<mode>_<timestamp>.jsonl, gzip-then-delete-raw on stop, delete-previous-.gz-for-that-mode on next start -- see mod_changelog.md v0.60.0) ===");
            SceneManager.sceneLoaded += OnSceneLoaded;
            Probe.DumpMenu("load");
            try
            {
                bool trivialOk = GeometryPatches.TestTrivialPatch();
                Log("[trivial-patch-test] patching our OWN no-op method: " + (trivialOk ? "OK" : "FAILED") +
                    "  (if this fails too, the problem is environment-wide, not specific to Part.InitializePart)");
            }
            catch (Exception e) { Log("[trivial-patch-test] threw: " + e.Message); }
            try
            {
                var harmony = new HarmonyLib.Harmony("sfs_probe.geometry_capture");
                bool geomOk = GeometryPatches.Apply(harmony);
                Log("geometry capture patch: " + (geomOk ? "OK" : "FAILED"));
            }
            catch (Exception e) { Log("harmony init FAILED: " + e.Message); }
            try
            {
                GameObject go = new GameObject("SFSProbeRunner");
                go.AddComponent<ProbeRunner>();
                UnityEngine.Object.DontDestroyOnLoad(go);
                Log("runner created");
            }
            catch (Exception e) { Log("runner create failed: " + e.Message); }
        }

        static void OnSceneLoaded(Scene s, LoadSceneMode m) { Probe.OnScene(s.name); }

        public static void Log(string msg)
        {
            try { Debug.Log("[SFSProbe] " + msg); } catch { }
            Append("probe.log", DateTime.Now.ToString("HH:mm:ss") + "  " + msg);
        }

        public static void Result(string msg)
        {
            Append("result.txt", DateTime.Now.ToString("HH:mm:ss") + "  " + msg);
            Log("-> " + msg);
        }

        public static void Append(string file, string line)
        {
            try { File.AppendAllText(Path.Combine(OutDir ?? ".", file), line + "\n"); }
            catch { }
        }
    }

    public class ProbeRunner : MonoBehaviour
    {
        float poll, retry;

        void Update()
        {
            try
            {
                if (Input.GetKeyDown(KeyCode.F9)) Probe.DumpFlight("F9");
                if (Input.GetKeyDown(KeyCode.Equals)) Probe.DumpFlight("=");
            } catch { }

            try
            {
                if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter))
                    Probe.StartRecording();
                if (Input.GetKeyDown(KeyCode.Backslash))
                    Probe.StopRecording();
            }
            catch { }

            // User-assignable key bindings (v0.48.0) -- see 'assignkey' command.
            try
            {
                if (Probe.KeyBindings.Count > 0)
                {
                    foreach (KeyCode kc in new List<KeyCode>(Probe.KeyBindings.Keys))
                    {
                        if (Input.GetKeyDown(kc))
                        {
                            string boundCmd = Probe.KeyBindings[kc];
                            try { Probe.Command(boundCmd); }
                            catch (Exception e) { ProbeMod.Result("ERROR (keybind " + kc + ") '" + boundCmd + "' " + e.Message); }
                        }
                    }
                }
            }
            catch { }

            poll += Time.deltaTime;
            if (poll > 0.5f) { poll = 0f; PollCommands(); }

            if (!Probe.WroteWorld)
            {
                retry += Time.deltaTime;
                if (retry > 2f) { retry = 0f; Probe.DumpWorld("retry"); }
            }
        }

        void FixedUpdate()
        {
            if (Probe.Telemetry) Probe.Sample();
            if (Probe.TelemetryJson) Probe.SampleJson();
            if (Probe.AutoStop) Probe.CheckAutoStop();
            if (Probe.Telemetry) Probe.CheckSeparation();
            Probe.CheckScript();
        }

        void PollCommands()
        {
            string path = Path.Combine(ProbeMod.OutDir ?? ".", "command.txt");
            string text;
            try
            {
                if (!File.Exists(path)) return;
                text = File.ReadAllText(path);
                File.Delete(path);
            }
            catch { return; }

            foreach (string raw in text.Split('\n'))
            {
                string line = raw.Trim();
                if (line.Length == 0) continue;
                try { Probe.Command(line); }
                catch (Exception e) { ProbeMod.Result("ERROR '" + line + "' " + e.Message); }
            }
        }
    }

    public static class Probe
    {
        public static bool WroteWorld;
        public static bool Telemetry;

        // ---------- live key -> command bindings (v0.48.0) ----------
        // Lets the person bind a key themselves at flight time (e.g. during
        // a manual test flight, when only THEY know the precise moment a
        // maneuver starts) rather than relying on Claude reacting to typed
        // narration, which is inherently a beat or two late. Checked in
        // ProbeRunner.Update() every frame (NOT FixedUpdate -- Input.GetKeyDown
        // is a one-frame-true edge and FixedUpdate's fixed cadence can miss it
        // at high framerate, same reason the existing F9/=/Enter/Backslash
        // hotkeys above are in Update()). Set via the 'assignkey' command,
        // e.g. "assignkey - rcsforce" runs the real 'rcsforce' command every
        // time '-' is pressed, until 'unassignkey -' or 'clearkeys'.
        public static Dictionary<KeyCode, string> KeyBindings = new Dictionary<KeyCode, string>();

        static readonly Dictionary<string, KeyCode> KeyAliases =
            new Dictionary<string, KeyCode>(StringComparer.OrdinalIgnoreCase)
        {
            {"-", KeyCode.Minus}, {"minus", KeyCode.Minus}, {"dash", KeyCode.Minus},
            {"=", KeyCode.Equals}, {"plus", KeyCode.Equals},
            {"[", KeyCode.LeftBracket}, {"]", KeyCode.RightBracket},
            {"\\", KeyCode.Backslash}, {"/", KeyCode.Slash},
            {".", KeyCode.Period}, {",", KeyCode.Comma},
            {";", KeyCode.Semicolon}, {"'", KeyCode.Quote}, {"`", KeyCode.BackQuote},
            {"space", KeyCode.Space}, {"spacebar", KeyCode.Space},
            {"enter", KeyCode.Return}, {"return", KeyCode.Return},
            {"tab", KeyCode.Tab},
            {"esc", KeyCode.Escape}, {"escape", KeyCode.Escape},
        };

        // Accepts real KeyCode names ("R", "F5", "LeftShift"), bare digits
        // ("5" -> Alpha5, since "5" alone isn't a valid KeyCode identifier),
        // and the symbol/word aliases above for keys that aren't valid C#
        // identifiers on their own (e.g. "-", "=", ".").
        internal static KeyCode? ParseKeyCode(string s)
        {
            if (string.IsNullOrEmpty(s)) return null;
            KeyCode alias;
            if (KeyAliases.TryGetValue(s, out alias)) return alias;
            if (s.Length == 1 && char.IsDigit(s[0]))
            {
                KeyCode alpha;
                if (Enum.TryParse<KeyCode>("Alpha" + s, true, out alpha)) return alpha;
            }
            KeyCode kc;
            if (Enum.TryParse<KeyCode>(s, true, out kc)) return kc;
            return null;
        }
        static int sampleCount;
        static int flightNumber;

        // JSON rocket-state snapshot recorder (v0.59.0) -- fully independent
        // lifecycle from the truth/inputs telemetry above. See 'telemetry json
        // on/off' in Command() and SampleJson()/BuildRocketJsonSnapshot() below.
        public static bool TelemetryJson;
        static int jsonSampleCount;
        static int jsonFlightNumber;
        static double lastJsonSnapshotT = double.NegativeInfinity;

        // Scoped-telemetry field spec (v0.29). null = default full-schema
        // recording (unchanged behavior). Non-null = only these fields are
        // sampled each tick, written to truth.jsonl alone (inputs.jsonl is
        // skipped entirely in this mode). Each entry is either a dotted
        // reflection path (e.g. "rb2d.mass", "location.velocity.x") walked
        // via ResolvePath, or "computed:NAME" for a registered multi-field
        // helper (e.g. "computed:dragArea") dispatched via AppendComputedField.
        // See Command()'s "telemetry" case for the command syntax.
        static string[] telemetryFields;

        // Auxiliary conditional triggers for scoped telemetry (v0.53.0+).
        // General "what/when/how often" control on top of the plain field
        // list: while <cond> is true, <command> fires -- once immediately,
        // then again every <intervalSeconds> (0 = only ever fires once per
        // recording). <cond> is evaluated via the exact same grammar/fields
        // "script" steps already use (GetScriptFieldValue + EvalOp), plus
        // two new pseudo-fields recognized there for this purpose:
        // "gimbaling" (1/0, true while any engine reports hasGimbal &&
        // gimbalOn) and "rcsfiring" (the live CountFiringThrusters count,
        // >0 while EITHER RCS selection path -- rotational or translational
        // -- is actually firing). Parsed by LoadTelemetryTriggers, checked
        // every scoped-telemetry tick by CheckTelemetryTriggers (see below,
        // near ScriptStep/CheckScript, the closest existing analog). See the
        // "telemetry" command case for the on-the-wire syntax.
        public class TelemetryTrigger
        {
            public string Field;
            public string Op;
            public double Value;
            public string Command;
            public double IntervalSeconds;
            public bool FiredOnce;
            public double NextAllowedTime;
        }
        static List<TelemetryTrigger> telemetryTriggers = new List<TelemetryTrigger>();

        // Zero-config default when "telemetry on <fields>" is given with no
        // "| ..." trigger block at all, or explicitly "| auto": the three
        // snapshots that used to need a manually-timed assignkey press, now
        // self-triggering and repeating on a slow cooldown instead of a
        // single shot, so a late-arriving condition (e.g. RCS engaging after
        // an earlier stage already separated) is never simply missed.
        const string DefaultTelemetryTriggerSpec =
            "gimbaling==1@3:gimbalinfo;rcsfiring>0@2:rcsforce;h<500@3:terrain";

        static void LoadTelemetryTriggers(string spec)
        {
            telemetryTriggers = new List<TelemetryTrigger>();
            string s = spec == null ? null : spec.Trim();
            if (string.IsNullOrEmpty(s) || s.Equals("auto", StringComparison.OrdinalIgnoreCase))
                s = DefaultTelemetryTriggerSpec;
            else if (s.Equals("none", StringComparison.OrdinalIgnoreCase))
                return;

            foreach (string rawStep in s.Split(';'))
            {
                string step = rawStep.Trim();
                if (step.Length == 0) continue;
                int colon = step.IndexOf(':');
                if (colon < 0) { ProbeMod.Log("[telemetry-trigger] bad step, missing ':': \"" + step + "\""); continue; }
                string condAndInterval = step.Substring(0, colon).Trim();
                string cmd = step.Substring(colon + 1).Trim();
                if (cmd.Length == 0) { ProbeMod.Log("[telemetry-trigger] bad step, empty command: \"" + step + "\""); continue; }

                double interval = 0;
                string condStr = condAndInterval;
                int at = condAndInterval.IndexOf('@');
                if (at >= 0)
                {
                    condStr = condAndInterval.Substring(0, at).Trim();
                    double.TryParse(condAndInterval.Substring(at + 1).Trim(),
                        NumberStyles.Float, CultureInfo.InvariantCulture, out interval);
                }

                string field, op; double value;
                if (!TryParseCondition(condStr, out field, out op, out value))
                { ProbeMod.Log("[telemetry-trigger] bad condition: \"" + condStr + "\""); continue; }

                telemetryTriggers.Add(new TelemetryTrigger
                {
                    Field = field, Op = op, Value = value,
                    Command = cmd, IntervalSeconds = interval
                });
            }
            ProbeMod.Log("[telemetry-trigger] loaded " + telemetryTriggers.Count + " trigger(s) from: " + s);
        }

        // Checked every scoped-telemetry tick (see Sample()). Fires via
        // Command(...) -- the exact same code path assignkey's own hotkey
        // handler already uses in ProbeRunner.Update() -- so none of
        // gimbalinfo/rcsforce/terrain/etc.'s own logic is duplicated here.
        static void CheckTelemetryTriggers(object r, double tNow)
        {
            if (telemetryTriggers == null || telemetryTriggers.Count == 0) return;
            foreach (TelemetryTrigger trig in telemetryTriggers)
            {
                double val = GetScriptFieldValue(r, trig.Field);
                if (double.IsNaN(val) || !EvalOp(trig.Op, val, trig.Value)) continue;

                if (trig.IntervalSeconds <= 0)
                {
                    if (trig.FiredOnce) continue;
                    trig.FiredOnce = true;
                }
                else
                {
                    if (tNow < trig.NextAllowedTime) continue;
                    trig.NextAllowedTime = tNow + trig.IntervalSeconds;
                }

                try { Command(trig.Command); }
                catch (Exception eAuto) { ProbeMod.Log("[telemetry-trigger] '" + trig.Command + "' threw: " + eAuto.Message); }
            }
        }

        public static bool AutoStop;
        static string autoStopMode = "turnover";   // "turnover" or "land"
        static float lastMass = float.NaN;
        static int flatMassTicks;
        static int fallingTicks;
        static bool hasBeenAirborne;
        static int groundedTicks;
        const int STOP_THRESHOLD_TICKS = 30;   // ~0.5s at 60Hz-equivalent sim time
        const float AIRBORNE_HEIGHT = 300f;    // must clear this once before landing-detect arms
        const float GROUND_HEIGHT = 30f;       // "near the ground" for landing-detect
        const float GROUND_SPEED = 3f;         // "stopped moving" for landing-detect

        public static void ResetAutoStopState()
        {
            lastMass = float.NaN;
            flatMassTicks = 0;
            fallingTicks = 0;
            hasBeenAirborne = false;
            groundedTicks = 0;
        }

        // Called every physics tick once autostop is armed. Two mutually
        // exclusive modes:
        //   turnover - fuel clearly out (mass flat ~0.5s) AND descending
        //              (vv<0 ~0.5s). The ascent-phase stop condition.
        //   land     - near the ground and nearly stationary for ~0.5s, but
        //              ONLY once the rocket has been observed above
        //              AIRBORNE_HEIGHT at some point -- otherwise this would
        //              fire immediately while still sitting on the pad, since
        //              "near ground, not moving" is also true before liftoff.
        public static void CheckAutoStop()
        {
            if (!Telemetry) return;
            try
            {
                object r = ActiveRocket();
                if (r == null) return;
                object loc = Unwrap(Get(r, "location"));
                object rb = Get(r, "rb2d");
                float mass = ToF(Get(rb, "mass"));
                float h = ToF(Get(loc, "Height"));
                float vv = ToF(Get(loc, "VerticalVelocity"));

                if (h > AIRBORNE_HEIGHT) hasBeenAirborne = true;

                if (autoStopMode == "land")
                {
                    if (hasBeenAirborne && h < GROUND_HEIGHT && Math.Abs(vv) < GROUND_SPEED)
                        groundedTicks++;
                    else
                        groundedTicks = 0;

                    if (groundedTicks >= STOP_THRESHOLD_TICKS)
                    {
                        ProbeMod.Log("[autostop] landing detected: h=" + h + " vv=" + vv +
                                     " grounded " + groundedTicks + " ticks -- stopping");
                        StopRecording();
                        AutoStop = false;
                    }
                    return;
                }

                // turnover mode (default)
                if (!float.IsNaN(lastMass) && Math.Abs(mass - lastMass) < 0.0005f) flatMassTicks++;
                else flatMassTicks = 0;
                lastMass = mass;

                if (vv < 0f) fallingTicks++;
                else fallingTicks = 0;

                if (flatMassTicks >= STOP_THRESHOLD_TICKS && fallingTicks >= STOP_THRESHOLD_TICKS)
                {
                    ProbeMod.Log("[autostop] turnover detected: mass flat " + flatMassTicks +
                                 " ticks, falling " + fallingTicks + " ticks -- stopping");
                    StopRecording();
                    AutoStop = false;
                }
            }
            catch (Exception e) { ProbeMod.Log("autostop check error: " + e.Message); }
        }

        public static void SetAutoStopMode(string mode)
        {
            autoStopMode = mode;
            ResetAutoStopState();
            AutoStop = true;
        }

        // Watches GameManager.rockets.Count every tick while recording. A rise
        // means a new rocket object just appeared -- a stage separation (or a
        // part breaking off) -- and ActiveRocket() will only ever follow ONE of
        // the resulting pieces afterward, silently losing the other's state.
        // This dumps EVERY rocket's full state (position, velocity, rotation,
        // angular velocity, mass) at the instant of the split, so a momentum-
        // conservation check has both sides of the event, not just whichever
        // piece the camera happens to keep following.
        static int lastRocketCount = -1;

        public static void CheckSeparation()
        {
            try
            {
                object gm = FindComponent("SFS.World.GameManager");
                var list = Get(gm, "rockets") as System.Collections.IEnumerable;
                if (list == null) return;
                int count = 0;
                var rockets = new List<object>();
                foreach (object r0 in list) { object r = Unwrap(r0); if (r != null) { rockets.Add(r); count++; } }

                if (lastRocketCount >= 0 && count > lastRocketCount)
                {
                    var sb = new StringBuilder();
                    sb.Append("{\"t\":").Append(Num(Time.timeSinceLevelLoad));
                    sb.Append(",\"rocketCountBefore\":").Append(lastRocketCount);
                    sb.Append(",\"rocketCountAfter\":").Append(count);
                    sb.Append(",\"rockets\":[");
                    bool first = true;
                    foreach (object r in rockets)
                    {
                        object loc = Unwrap(Get(r, "location"));
                        object rb = Get(r, "rb2d");
                        object worldPos = GetWrapped(loc, "position");
                        object worldVel = GetWrapped(loc, "velocity");
                        object holder = Get(r, "partHolder");
                        object parts = Get(holder, "parts");
                        var pc = parts as System.Collections.ICollection;
                        if (!first) sb.Append(",");
                        first = false;
                        sb.Append("{\"partCount\":").Append(pc != null ? pc.Count : -1);
                        sb.Append(",\"mass\":").Append(Num(Get(rb, "mass")));
                        sb.Append(",\"px\":").Append(Num(Get(worldPos, "x")));
                        sb.Append(",\"py\":").Append(Num(Get(worldPos, "y")));
                        sb.Append(",\"vx\":").Append(Num(Get(worldVel, "x")));
                        sb.Append(",\"vy\":").Append(Num(Get(worldVel, "y")));
                        sb.Append(",\"rot\":").Append(Num(Get(rb, "rotation")));
                        sb.Append(",\"angv\":").Append(Num(Get(rb, "angularVelocity")));
                        sb.Append("}");
                    }
                    sb.Append("]}");
                    ProbeMod.Append("separation_events.jsonl", sb.ToString());
                    ProbeMod.Log("[separation] rocket count " + lastRocketCount + " -> " + count + ", dumped all pieces");
                }
                lastRocketCount = count;
            }
            catch (Exception e) { ProbeMod.Log("separation check error: " + e.Message); }
        }

        // ---------- scripted flight plans (v0.40) ----------
        //
        // Removes Claude's own round-trip latency from a multi-checkpoint
        // flight plan: instead of polling telemetry and sending each command
        // individually (seconds of real-world latency and inconsistent
        // timing per step), the WHOLE plan is armed in one 'script' command
        // and checked every physics tick (60Hz) inside FixedUpdate, right
        // alongside Sample()/CheckAutoStop(). Each step fires exactly once,
        // the instant its condition is true.
        //
        // Syntax: "script <cond1>:<cmd1a> && <cmd1b>; <cond2>:<cmd2>; ..."
        // Example: "script h>=1000:setrot 5; h>=5000:setrot 10; h>=25000:setrot 70"
        // <cond> is "<field><op><value>" with op in {>=,<=,==,!=,>,<} (checked
        // longest-first so ">=" isn't misread as ">"). <field> is one of the
        // short telemetry names (h, vv, t, m, v, rot, angv, partCount) or any
        // dot-path ResolvePath already understands (e.g. "rb2d.mass"), tried
        // as a fallback. No JSON parser -- kept to this codebase's existing
        // plain-text comma/semicolon command style on purpose.
        //
        // Deliberately NOT sequential/ordered: every step's condition is
        // checked independently every tick, so out-of-order or simultaneous
        // triggers are both handled correctly -- fine for a monotonically
        // increasing field like altitude during ascent, and safe in general.
        public class ScriptStep
        {
            public string Field;
            public string Op;
            public double Value;
            public string[] Commands;
            public bool Done;
        }
        public static List<ScriptStep> ScriptQueue = new List<ScriptStep>();

        public static void CheckScript()
        {
            if (ScriptQueue.Count == 0) return;
            try
            {
                object r = ActiveRocket();
                if (r == null) return;
                foreach (ScriptStep step in ScriptQueue)
                {
                    if (step.Done) continue;
                    double val = GetScriptFieldValue(r, step.Field);
                    if (double.IsNaN(val)) continue;
                    if (!EvalOp(step.Op, val, step.Value)) continue;

                    step.Done = true;
                    ProbeMod.Log("[script] triggered: " + step.Field + step.Op + step.Value +
                                 " (actual=" + val + ") -> " + string.Join(" && ", step.Commands));
                    foreach (string cmd in step.Commands)
                    {
                        try { Command(cmd); }
                        catch (Exception e) { ProbeMod.Log("[script] step command '" + cmd + "' threw: " + e.Message); }
                    }
                }
            }
            catch (Exception e) { ProbeMod.Log("[script] check error: " + e.Message); }
        }

        static int LoadScript(string spec)
        {
            ScriptQueue.Clear();
            string[] stepsRaw = spec.Split(';');
            int count = 0;
            foreach (string raw in stepsRaw)
            {
                string s = raw.Trim();
                if (s.Length == 0) continue;
                int colonIdx = s.IndexOf(':');
                if (colonIdx < 0) throw new Exception("step missing ':' separator: \"" + s + "\"");
                string condPart = s.Substring(0, colonIdx).Trim();
                string cmdPart = s.Substring(colonIdx + 1).Trim();

                string field, op; double value;
                if (!TryParseCondition(condPart, out field, out op, out value))
                    throw new Exception("couldn't parse condition: \"" + condPart + "\"");

                string[] commands = cmdPart.Split(new string[] { "&&" }, StringSplitOptions.RemoveEmptyEntries);
                for (int i = 0; i < commands.Length; i++) commands[i] = commands[i].Trim();
                if (commands.Length == 0) throw new Exception("step has no command: \"" + s + "\"");

                ScriptQueue.Add(new ScriptStep { Field = field, Op = op, Value = value, Commands = commands, Done = false });
                count++;
            }
            return count;
        }

        static bool TryParseCondition(string cond, out string field, out string op, out double value)
        {
            field = null; op = null; value = 0;
            // Longest-first so ">="/"<="/"=="/"!=" aren't misread as ">"/"<".
            string[] ops = new string[] { ">=", "<=", "==", "!=", ">", "<" };
            foreach (string o in ops)
            {
                int idx = cond.IndexOf(o, StringComparison.Ordinal);
                if (idx > 0)
                {
                    field = cond.Substring(0, idx).Trim();
                    op = o;
                    string valStr = cond.Substring(idx + o.Length).Trim();
                    return double.TryParse(valStr, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
                }
            }
            return false;
        }

        static bool EvalOp(string op, double a, double b)
        {
            switch (op)
            {
                case ">=": return a >= b;
                case "<=": return a <= b;
                case ">": return a > b;
                case "<": return a < b;
                case "==": return a == b;
                case "!=": return a != b;
                default: return false;
            }
        }

        // Short telemetry-style field names (matching truth.jsonl's own
        // naming) resolved directly for the common cases; anything else falls
        // back to ResolvePath's dot-path walker (same mechanism scoped
        // telemetry already uses), so "rb2d.mass" or "location.velocity.x"
        // work too, no new resolution logic needed.
        static double GetScriptFieldValue(object rocket, string field)
        {
            try
            {
                object loc = Unwrap(Get(rocket, "location"));
                switch (field)
                {
                    case "h": return ToD(Get(loc, "Height"));
                    case "vv": return ToD(Get(loc, "VerticalVelocity"));
                    case "t": return ToD(Get(loc, "time"));
                    case "m": return ToD(Get(Get(rocket, "rb2d"), "mass"));
                    case "rot": return ToD(Get(Get(rocket, "rb2d"), "rotation"));
                    case "angv": return ToD(Get(Get(rocket, "rb2d"), "angularVelocity"));
                    // Two pseudo-fields added for telemetry auxiliary triggers
                    // (v0.53.0+) -- harmless to expose to "script" steps too,
                    // same evaluator, no separate code path.
                    case "gimbaling":
                    {
                        bool gOnGSV; float gA, gB, gC, gD;
                        return (TryGetPrimaryGimbal(rocket, out gOnGSV, out gA, out gB, out gC, out gD) && gOnGSV) ? 1.0 : 0.0;
                    }
                    case "rcsfiring": return CountFiringThrusters(rocket);
                    case "v":
                    {
                        object velocity = GetWrapped(loc, "velocity");
                        double vx = ToD(Get(velocity, "x"));
                        double vy = ToD(Get(velocity, "y"));
                        return Math.Sqrt(vx * vx + vy * vy);
                    }
                    case "partCount":
                    {
                        object holder = Get(rocket, "partHolder");
                        object parts = Get(holder, "parts");
                        var c = parts as System.Collections.ICollection;
                        return c != null ? c.Count : -1;
                    }
                    default:
                        return ToD(ResolvePath(rocket, field));
                }
            }
            catch { return double.NaN; }
        }

        public static void OnScene(string n) { WroteWorld = false; DumpWorld("scene:" + n); }

        // ---------- hotkey recording ----------

        public static void StartRecording(string[] fields = null, string triggerSpec = null)
        {
            if (Telemetry) return;
            flightNumber++;
            sampleCount = 0;
            lastRocketCount = -1;   // fresh baseline each flight -- avoids a false
                                    // separation trigger from leftover debris or
                                    // the previous recording's rocket count
            telemetryFields = fields;
            LoadTelemetryTriggers(triggerSpec);
            // v0.60.0 unified archive lifecycle: discard any stray leftover live
            // file from an uncleanly-stopped previous recording (rare -- e.g. a
            // crash), then delete the LAST COMPLETED run's archive for this mode.
            // New runs overwrite previous results by design; a flight that needs
            // to survive this must be tagged via sfsprobe_tag_flight, which copies
            // it into archive/kept/ BEFORE it can be deleted here.
            ClearLiveFile("sample.jsonl");
            DeletePreviousArchive("flat");
            Telemetry = true;
            string scopeNote = fields == null ? "full" : ("scoped[" + fields.Length + "]: " + string.Join(",", fields));
            ProbeMod.Result("[hotkey] recording STARTED  flight #" + flightNumber + "  mode=" + scopeNote);
        }

        public static void StopRecording()
        {
            if (!Telemetry) return;
            Telemetry = false;
            string a1 = ArchiveOne("sample.jsonl", "flat");
            ProbeMod.Result("[hotkey] recording STOPPED  flight #" + flightNumber +
                             "  samples=" + sampleCount +
                             "  -> " + (a1 ?? "(no samples)"));
            telemetryFields = null;   // next hotkey (Enter) always starts back in full mode
        }

        // ---------- JSON rocket-state snapshot recorder (v0.59.0, lifecycle
        // unified with flat mode in v0.60.0) ----------
        // 'telemetry json on' / 'telemetry json off' -- see the "telemetry"
        // command case and SampleJson()/BuildRocketJsonSnapshot() for the full
        // design writeup. Deliberately a SEPARATE bool/lifecycle from
        // Telemetry above: can run alongside scoped/full flat telemetry, or
        // entirely on its own, since it answers a different question ("what
        // does the rocket structurally look like right now") at a much
        // slower, deliberately un-synced cadence (~1 Hz) than the physics
        // telemetry (~60 Hz). Archive tag is "parts" (renamed from
        // "rocketstate" in v0.60.0 to match the flat/parts mode-naming
        // convention the archive lifecycle now shares with flat mode).
        public static void StartJsonRecording()
        {
            if (TelemetryJson) return;
            jsonFlightNumber++;
            jsonSampleCount = 0;
            lastJsonSnapshotT = double.NegativeInfinity;   // force an immediate first snapshot
            ClearLiveFile("rocketstate.jsonl");
            DeletePreviousArchive("parts");
            TelemetryJson = true;
            ProbeMod.Result("[json] recording STARTED  flight #" + jsonFlightNumber + "  ~1 Hz -> rocketstate.jsonl");
        }

        public static void StopJsonRecording()
        {
            if (!TelemetryJson) return;
            TelemetryJson = false;
            string a3 = ArchiveOne("rocketstate.jsonl", "parts");
            ProbeMod.Result("[json] recording STOPPED  flight #" + jsonFlightNumber +
                             "  samples=" + jsonSampleCount +
                             "  -> " + (a3 ?? "(no rocketstate)"));
        }

        // ================================================================
        //  Self-description registry (v0.57.0, MCP overhaul Checkpoint 1)
        // ----------------------------------------------------------------
        // Structured, honest metadata for every real command and every
        // real computed-telemetry-field output key -- the new PRIMARY
        // source of truth for "what commands/fields exist and what do
        // they mean", superseding sfsprobe_mcp/server.py's regex-parsed
        // comments (which remain only as a fallback, used when the game
        // isn't running, and as a drift auditor). Dumped live via the new
        // 'describe' command below. See docs/mcp_overhaul_checkpoint_
        // prompt.md Checkpoint 1 for full design rationale -- in
        // particular: Unit is REQUIRED and reflects the REAL computed
        // unit, never what the key's name implies. This directly targets
        // the parachuteAlphaDeg-is-actually-an-angular-acceleration class
        // of bug that motivated this whole registry.
        // Additive only -- built by reading every existing case block
        // below, without changing any of their logic.
        // ================================================================

        public struct ProbeCommandInfo
        {
            public string Name;
            public string Syntax;
            public string Description;
            public string Category;
        }

        public struct ProbeFieldInfo
        {
            public string Key;
            // Which of the four telemetry field namespaces this entry lives in:
            //   "script-condition" -- GetScriptFieldValue, script/trigger conditions only
            //   "computed"         -- AppendComputedField groups, requested as
            //                         computed:<Group> in a scoped 'telemetry on <fields>' list
            //   "truth"            -- BuildTruthSample, full-schema 'telemetry on' (no field
            //                         list), written to truth.jsonl
            //   "inputs"           -- BuildInputsSample, full-schema only, written to inputs.jsonl
            public string Namespace;
            // Non-empty only for "computed" entries: the computed:<Group> name that
            // produces this key alongside its sibling keys in the same group.
            public string Group;
            public string Unit;
            public string Description;
            // How a caller actually reaches this exact value -- the same field NAME
            // can exist in more than one namespace via a genuinely different code
            // path (e.g. h/vv/t/m/rot/angv/partCount all exist in both
            // "script-condition" and "truth"; they agree on the value but are NOT
            // the same mechanism, and scoped-mode 'telemetry on <fields>' does NOT
            // go through "truth"'s code at all -- see Checkpoint 1 catalog
            // Uncertainty #1).
            public string RequestAs;
        }

        public static readonly ProbeCommandInfo[] CommandRegistry = new ProbeCommandInfo[]
        {
            new ProbeCommandInfo { Name = "ping", Category = "diagnostics",
                Syntax = "ping",
                Description = "Liveness check. Returns scene name, active rocket count, Time.fixedDeltaTime, game version, mod version." },
            new ProbeCommandInfo { Name = "snapshot", Category = "diagnostics",
                Syntax = "snapshot",
                Description = "Forces an immediate full-schema flight dump (DumpFlight), independent of the polling/telemetry loop." },
            new ProbeCommandInfo { Name = "world", Category = "diagnostics",
                Syntax = "world",
                Description = "Forces an immediate world dump (DumpWorld), resetting the 'already wrote world once' guard so it re-dumps even if unchanged." },
            new ProbeCommandInfo { Name = "menu", Category = "diagnostics",
                Syntax = "menu",
                Description = "Forces an immediate menu-state dump (DumpMenu)." },
            new ProbeCommandInfo { Name = "telemetry", Category = "telemetry",
                Syntax = "telemetry on | telemetry on <field1>,<field2>,... [| <cond>@<sec>:<cmd>; ...] | telemetry off | telemetry json on | telemetry json off",
                Description = "Starts/stops per-tick recording to a single live file (sample.jsonl) merging truth+input fields into one JSON object per tick (v0.60.0: truth.jsonl/inputs.jsonl split removed -- one record per tick, not two). No field list = full schema (every field this mod knows). A field list = scoped mode, one row per tick, computed:<name> allowed. Optional '| ...' suffix adds auxiliary triggers that fire on-demand commands while a script-condition expression holds true ('| auto' = built-in default, '| none' = disabled). Second word must be 'on', 'off', 'json', or omitted (defaults to 'off') -- v0.58.0+ rejects an unrecognized word as an error instead of silently stopping recording. On 'off', the live file is archived to archive/telemetry_flat_<timestamp>.jsonl.gz (gzipped, raw deleted immediately -- JSON only lives on disk during the run). The NEXT 'telemetry on' deletes that .gz first: new runs overwrite previous results. Use sfsprobe_tag_flight to copy a .gz into archive/kept/ before it's superseded, if it needs to survive. SEPARATELY, 'telemetry json on'/'telemetry json off' (v0.59.0) starts/stops an independent ~1Hz full per-part JSON rocket-state snapshot recorder to rocketstate.jsonl, archived the same way under tag 'parts' (archive/telemetry_parts_<timestamp>.jsonl.gz) -- its own lifecycle, can run alongside or instead of the above. See the 'field' domain for its per-part schema (id/name/mass/resourcePercent/temperature)." },
            new ProbeCommandInfo { Name = "throttle", Category = "control",
                Syntax = "throttle <0-1 float>",
                Description = "Sets throttlePercent (amount only). Does NOT touch master ignition (throttleOn)." },
            new ProbeCommandInfo { Name = "master", Category = "control",
                Syntax = "master on | master off",
                Description = "Sets rocket-wide throttleOn (master ignition 'start'), independent of throttle amount and per-engine engineOn." },
            new ProbeCommandInfo { Name = "diag", Category = "diagnostics",
                Syntax = "diag",
                Description = "Per-part index + count of EngineModules found via ModuleValues, for cross-checking against the snapshot dump's own part/engine counts." },
            new ProbeCommandInfo { Name = "autostop", Category = "control",
                Syntax = "autostop on | autostop turnover | autostop land | autostop off",
                Description = "Arms/disarms the probe's own autostop-on-condition behavior. 'on'/'turnover' = ascent-phase auto-stop, 'land' = descent-phase auto-stop, 'off' = disarm." },
            new ProbeCommandInfo { Name = "ignite", Category = "control",
                Syntax = "ignite",
                Description = "Sets EngineModule.engineOn = true on every engine on the active rocket (bypasses staging). Independent of throttle amount and master ignition." },
            new ProbeCommandInfo { Name = "revert", Category = "control",
                Syntax = "revert",
                Description = "Calls GameManager.RevertToLaunch(false) via reflection." },
            new ProbeCommandInfo { Name = "achievements", Category = "diagnostics",
                Syntax = "achievements",
                Description = "Dumps every SFS.Logs.Challenge (id, title, description, planet, difficulty, returnSafely, stepCount) plus which are complete for the active save. Writes sfs_probe_achievements.json. Not a Steamworks achievement -- purely in-game state." },
            new ProbeCommandInfo { Name = "geometry", Category = "diagnostics",
                Syntax = "geometry",
                Description = "Dumps whatever GeometryCapture has passively captured so far (a Harmony postfix on Part.InitializePart). Never triggers capture itself; largely superseded by dragarea/aerotorque's direct-call path, kept for reference. Writes sfs_probe_geometry.json." },
            new ProbeCommandInfo { Name = "dragarea", Category = "physics-query",
                Syntax = "dragarea",
                Description = "One-shot dump of the real dragArea/center-of-drag via direct reflection calls into the game's own Aero_Rocket.GetDragSurfaces -> AeroModule.GetExposedSurfaces -> AeroModule.CalculateDragForce chain. Includes up to 10 sample raw segments. Writes sfs_probe_dragarea.json." },
            new ProbeCommandInfo { Name = "dragareasweep", Category = "physics-query",
                Syntax = "dragareasweep <comma-separated AoA degrees, no spaces>",
                Description = "Reads the game's own REAL drag computation (same reflection chain as dragarea) at a whole list of caller-chosen SYNTHETIC AoA values in one call -- e.g. 'dragareasweep -90,-60,-30,0,30,60,90,120,150,180'. No actual flying through those angles required; works on a stationary craft on the pad. Built to replace empirically fitting an AoA table from noisy finite-differenced flight velocity -- this reads the exact, complete-coverage answer straight from the game for any angle. dragCopX/Y are in the same velocity-aligned frame as computed:dragArea's dragCopX/Y. Writes sfs_probe_dragareasweep.json." },
            new ProbeCommandInfo { Name = "loadblueprint", Category = "blueprint",
                Syntax = "loadblueprint <path with possible spaces>",
                Description = "World_PC ONLY. Deserializes a Blueprint JSON file and spawns it as an ADDITIONAL live physics rocket via RocketManager.SpawnBlueprint. NOT safe for routine mid-flight use (moves the camera, no cost/achievement tracking, functionally a cheat if used repeatedly)." },
            new ProbeCommandInfo { Name = "loadblueprintbuild", Category = "blueprint",
                Syntax = "loadblueprintbuild <path with possible spaces>",
                Description = "Build_PC ONLY. Loads a Blueprint JSON into the editor via BuildState.LoadBlueprint, REPLACING the current design (calls BuildState.Clear() first). Pre-validates part names against the live parts catalog before calling, since Clear() runs before any other failure can be detected." },
            new ProbeCommandInfo { Name = "getplacedmagnets", Category = "blueprint",
                Syntax = "getplacedmagnets",
                Description = "Build_PC ONLY, needs at least one part placed. Dumps MagnetModule.points for every ACTUALLY PLACED part in the editor (not bare catalog prefabs -- see getparts for that). Writes sfs_probe_placed_magnets.json." },
            new ProbeCommandInfo { Name = "dumpblueprint", Category = "blueprint",
                Syntax = "dumpblueprint",
                Description = "Reads the CURRENT editor design as a real Blueprint via BuildState.main.GetBlueprint(true), serialized with the game's own JsonWrapper.ToJson. Writes sfs_probe_current_blueprint.json. Reliable way to get real per-part properties instead of guessing." },
            new ProbeCommandInfo { Name = "getparts", Category = "blueprint",
                Syntax = "getparts",
                Description = "Full parts-catalog index: for every catalog part (not a placed instance), name/mass/centerOfMass/parametric variables/magnet points, plus PartsLoader.partVariants. Deliberately NOT run automatically on scene load -- heavier, command-gated. Writes sfs_probe_parts_index.json." },
            new ProbeCommandInfo { Name = "aeroformula", Category = "physics-query",
                Syntax = "aeroformula",
                Description = "Reads the 4 serialized AeroFormula coefficients (velPow, densityPow, tempOffset, m) AeroModule.GetTemperature needs -- live Unity-serialized data, not IL literals. Writes sfs_probe_aeroformula.json." },
            new ProbeCommandInfo { Name = "atmophysics", Category = "physics-query",
                Syntax = "atmophysics",
                Description = "Reads the active rocket's current planet's atmospherePhysics block: height/density/curve (already difficulty-scaled) plus minHeatingVelocityMultiplier and shockwaveIntensity. Writes sfs_probe_atmophysics.json." },
            new ProbeCommandInfo { Name = "terrain", Category = "physics-query",
                Syntax = "terrain | terrain <comma-separated degree offsets, e.g. -30,-10,0,10,30>",
                Description = "Real per-angle terrain height sweep around the craft's current angular position via Planet.GetTerrainHeightAtAngles (clampToWater true and false), plus a cross-check against Location.GetTerrainHeight. Writes sfs_probe_terrain.json." },
            new ProbeCommandInfo { Name = "terraingeo", Category = "physics-query",
                Syntax = "terraingeo",
                Description = "GetTerrainNormal (actually returns a TANGENT vector along the surface in global XY, not a perpendicular normal -- misnamed in the game's own API), GetTerrainColor, IsInsideTerrain (at the real craft position, a synthetic point below the surface, and one far above maxTerrainHeight), GetMaxLOD. Writes sfs_probe_terraingeo.json." },
            new ProbeCommandInfo { Name = "difficulty", Category = "physics-query",
                Syntax = "difficulty",
                Description = "Reads the actual difficulty-scaled heat multipliers (HeatVelocityMultiplier, MinHeatVelocityMultiplier, IspMultiplier, DryMassMultiplier) instead of assuming Normal=1.0, plus aeroData.testShock/testReentry debug-override flags. Writes sfs_probe_difficulty.json." },
            new ProbeCommandInfo { Name = "jointgraph", Category = "physics-query",
                Syntax = "jointgraph",
                Description = "Dumps the live joint connectivity graph (Rocket.jointsGroup.joints): each PartJoint is an undirected edge (part A name, part B name, anchor position), no strength/type field. Writes sfs_probe_jointgraph.json." },
            new ProbeCommandInfo { Name = "turn", Category = "control",
                Syntax = "turn <float>",
                Description = "Writes arrowkeys.turnAxis directly -- the same state Rocket.ApplyTorque reads. No clamp applied. Has zero physical effect via the torque path on a rocket with no TorqueModule (e.g. no RCS/reaction wheel); the only remaining path is gimbal deflection while an engine's throttle_Out > 0." },
            new ProbeCommandInfo { Name = "setrot", Category = "control",
                Syntax = "setrot <degrees>",
                Description = "INSTANT snap -- writes rb2d.rotation directly (degrees) and zeroes rb2d.angularVelocity. Does not simulate getting there." },
            new ProbeCommandInfo { Name = "script", Category = "scripting",
                Syntax = "script <spec> (rest of line, unsplit -- see LoadScript for full condition/command grammar)",
                Description = "Arms a queued conditional flight plan, evaluated tick-by-tick via GetScriptFieldValue/EvalOp." },
            new ProbeCommandInfo { Name = "scriptstatus", Category = "scripting",
                Syntax = "scriptstatus",
                Description = "Dumps pending/done counts and each queued step's field/op/value/commands/done state." },
            new ProbeCommandInfo { Name = "scriptclear", Category = "scripting",
                Syntax = "scriptclear",
                Description = "Clears the script queue." },
            new ProbeCommandInfo { Name = "rcsinfo", Category = "physics-query",
                Syntax = "rcsinfo",
                Description = "Static per-RcsModule dump: directionAngleThreshold, torqueAngleThreshold, thrust, ISP, local thrustPosition, per-thruster local thrustNormal. Empty (0 modules) if the rocket has no RCS parts. Writes sfs_probe_rcsinfo.json." },
            new ProbeCommandInfo { Name = "rcsforce", Category = "physics-query",
                Syntax = "rcsforce",
                Description = "Live replication of RcsModule.FixedUpdate's exact per-module force/mass-flow computation, calling the SAME private TorqueThrust/DirectionThrust selection methods via reflection (not a reimplementation): per-thruster firing decision, world-space thrust normal, per-module predicted force and mass flow, plus a rocket-wide total. Writes sfs_probe_rcsforce.json." },
            new ProbeCommandInfo { Name = "aerotorque", Category = "physics-query",
                Syntax = "aerotorque",
                Description = "On-demand version of TryComputeAeroTorque: dragArea, air density, drag force vector, center-of-drag (world space and post-20%-lerp), world center of mass, rb2d.inertia, predicted torque, predictedAngularAccelDegPerSec2. NOT valid mid-parachute-deployment. Writes sfs_probe_aerotorque.json." },
            new ProbeCommandInfo { Name = "gimbalinfo", Category = "physics-query",
                Syntax = "gimbalinfo",
                Description = "Full commanded-steering -> gimbal-angle chain dump per gimbaling EngineModule: gimbalOn, throttleOut, turnAxisInput, time/targetTime (unitless 0-1 animation-progress fractions, NOT seconds or degrees), animationTime (seconds), unscaledTime flag, and the real rotate-curve keyframes. Writes sfs_probe_gimbalinfo.json. Reports 'no gimbaling engines found' if none have hasGimbal." },
            new ProbeCommandInfo { Name = "getforwardstartinfo", Category = "physics-query",
                Syntax = "getforwardstartinfo [optional_name_no_spaces]",
                Description = "Full static craft-config snapshot for forward_sim.py's Python integrator: rocket mass, rb2d.inertia, world center of mass, rotation, summed enabled torque, plus per-part arrays for engines/RCS modules/parachutes. Known scope limits (in-code): engine 'scale' term hardcoded to 1.0 (exact only for unscaled parts); positionLocalBody valid only until the next staging event. Call before ignition for the cleanest read. Writes sfs_probe_forwardstartinfo.json. ALSO (v0.62.0+) writes a full 721-sample, 0.5-degree-resolution real AoA-vs-dragArea/CoP table for this exact craft to AoA_drag_table_<name>.json (same mechanism as 'dragareasweep', run at full resolution automatically). <name> is an OPTIONAL arg (e.g. 'getforwardstartinfo one_engine_gimbal_test') that overrides the real Rocket.rocketName -- needed because a craft's real name is blank until it's been named+launched, by which point this pre-ignition snapshot has already been taken; falls back to rocketName (or 'unknown') if omitted." },
            new ProbeCommandInfo { Name = "parachutedrag", Category = "physics-query",
                Syntax = "parachutedrag",
                Description = "On-demand version of TryComputeParachuteDrag -- same shape as aerotorque but with the confirmed chute-compounding step applied on top. chutesActive:0 harmlessly reduces to the plain aero-torque case if no chute is deployed. Writes sfs_probe_parachutedrag.json." },
            new ProbeCommandInfo { Name = "assignkey", Category = "keybind",
                Syntax = "assignkey <key> <full command string, including its own args>",
                Description = "Binds a keyboard key so the PLAYER can trigger any probe command at a precise moment (e.g. exact full deflection), dispatched through the normal Command() path." },
            new ProbeCommandInfo { Name = "unassignkey", Category = "keybind",
                Syntax = "unassignkey <key>",
                Description = "Removes one key binding." },
            new ProbeCommandInfo { Name = "listkeys", Category = "keybind",
                Syntax = "listkeys",
                Description = "Lists all active key -> command bindings." },
            new ProbeCommandInfo { Name = "clearkeys", Category = "keybind",
                Syntax = "clearkeys",
                Description = "Removes all key bindings." },
            new ProbeCommandInfo { Name = "airtemp", Category = "physics-query",
                Syntax = "airtemp",
                Description = "One-shot real-time read of AeroModule.GetTemperatureAndShockwave's actual air-temperature output for the active rocket (same helper the realAirTemp truth field uses), without needing telemetry recording active." },
            new ProbeCommandInfo { Name = "telemetrysnapshot", Category = "telemetry",
                Syntax = "telemetrysnapshot | telemetrysnapshot <comma-separated fields, no spaces>",
                Description = "A genuine one-tick peek: builds exactly the same inputs/truth JSON a real recorded sample would contain (via the SAME BuildInputsSample/BuildTruthSample functions Sample() itself uses) WITHOUT touching Telemetry state, sampleCount, or either file. Works whether recording is on, off, or already running. No args: full inputs+truth dump (unchanged pre-v0.63.0 behavior). With args (v0.63.0): scoped mode, e.g. 'telemetrysnapshot rb2d.angularDrag,rb2d.inertia' -- same field syntax as 'telemetry on <fields>' (computed:, partCount, plain dot-paths), via the SAME BuildScopedSample() real scoped recording uses, so an ad-hoc field check doesn't need a full telemetry on/off round trip. Writes sfs_probe_telemetry_snapshot.json." },
            new ProbeCommandInfo { Name = "cheat", Category = "control",
                Syntax = "cheat <ExactCaseSensitiveCheatName> (e.g. 'cheat InfiniteFuel')",
                Description = "Calls SandboxSettings.main.Toggle<arg>() via reflection. arg is deliberately NOT lowercased -- reflection method-name lookup is case-sensitive. Known gap: InfiniteOxygen can never work (a UI button exists but no matching Toggle... method on SandboxSettings -- a real naming inconsistency in the game itself, not fixable probe-side). Valid <arg> values are whatever Toggle* methods exist on the live SandboxSettings type; not enumerable statically." },
            new ProbeCommandInfo { Name = "describe", Category = "diagnostics",
                Syntax = "describe",
                Description = "Dumps this entire self-description registry (every command + every telemetry field, across all 4 namespaces, each with its real unit/type) as JSON. Writes sfs_probe_describe.json. Call this FIRST, before guessing at any command or field name -- it is the live, authoritative source of truth, current as of this exact running mod build." },
        };

        public static readonly ProbeFieldInfo[] FieldRegistry = new ProbeFieldInfo[]
        {
            // ---- Namespace: script-condition (GetScriptFieldValue) ----
            // Used by script/telemetry's auxiliary-trigger condition grammar
            // (<field><op><value>), NOT by scoped telemetry's field list.
            new ProbeFieldInfo { Key = "h", Namespace = "script-condition", Unit = "meters",
                Description = "location.Height", RequestAs = "script/trigger condition only, e.g. 'h<1000@0:cmd'" },
            new ProbeFieldInfo { Key = "vv", Namespace = "script-condition", Unit = "m/s",
                Description = "location.VerticalVelocity", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "t", Namespace = "script-condition", Unit = "seconds",
                Description = "location.time", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "m", Namespace = "script-condition", Unit = "tonnes",
                Description = "rb2d.mass", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "rot", Namespace = "script-condition", Unit = "degrees",
                Description = "rb2d.rotation", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "angv", Namespace = "script-condition", Unit = "deg/s",
                Description = "rb2d.angularVelocity", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "gimbaling", Namespace = "script-condition", Unit = "bool (1.0/0.0)",
                Description = "1.0 iff TryGetPrimaryGimbal finds an ON gimbaling engine (v0.53.0+)", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "rcsfiring", Namespace = "script-condition", Unit = "count (float)",
                Description = "CountFiringThrusters(rocket) -- number of RCS thrusters currently firing (targetTime > 0.5)", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "v", Namespace = "script-condition", Unit = "m/s",
                Description = "sqrt(vx^2+vy^2) from location.velocity", RequestAs = "script/trigger condition only" },
            new ProbeFieldInfo { Key = "partCount", Namespace = "script-condition", Unit = "count (int, -1 on failure)",
                Description = "partHolder.parts.Count", RequestAs = "script/trigger condition only -- for SCOPED telemetry, this same name is handled by a separate dedicated special-case, see the 'truth' namespace entry below" },

            // ---- Namespace: computed (AppendComputedField groups) ----
            // Requested in scoped 'telemetry on ...' field lists as computed:<Group>.
            // Each group appends multiple named JSON keys per tick. Highest-value
            // registry entries -- several key names are misleading vs. their real unit.
            new ProbeFieldInfo { Key = "dragArea", Namespace = "computed", Group = "dragArea", Unit = "m^2-equivalent (drag-force scale per sfs_physics_reference.md 2.3)",
                Description = "TryComputeDragArea's drag magnitude; null if the reflection chain failed", RequestAs = "telemetry on ...,computed:dragArea" },
            new ProbeFieldInfo { Key = "dragCopX", Namespace = "computed", Group = "dragArea", Unit = "world-space meters",
                Description = "center-of-drag x, PRE-Lerp (raw exposed-surface-weighted CoP, not yet blended 20% toward CoM)", RequestAs = "telemetry on ...,computed:dragArea" },
            new ProbeFieldInfo { Key = "dragCopY", Namespace = "computed", Group = "dragArea", Unit = "world-space meters",
                Description = "center-of-drag y, PRE-Lerp", RequestAs = "telemetry on ...,computed:dragArea" },
            new ProbeFieldInfo { Key = "dragSurfaces", Namespace = "computed", Group = "dragArea", Unit = "count (int)",
                Description = "total raw drag surfaces before occlusion filtering", RequestAs = "telemetry on ...,computed:dragArea" },
            new ProbeFieldInfo { Key = "dragExposed", Namespace = "computed", Group = "dragArea", Unit = "count (int)",
                Description = "surfaces remaining after GetExposedSurfaces occlusion filtering", RequestAs = "telemetry on ...,computed:dragArea" },
            new ProbeFieldInfo { Key = "engines", Namespace = "computed", Group = "engines", Unit = "array of objects",
                Description = "Per-part array; each element is {part,type,...} where type='engine' (engineOn bool, thrustDirX/Y unit direction, gimbalOn bool, throttleOut 0-1 float) or type='booster' (boosterPrimed bool, thrustVectorX/Y)", RequestAs = "telemetry on ...,computed:engines" },
            new ProbeFieldInfo { Key = "heatParts", Namespace = "computed", Group = "heatParts", Unit = "array of objects",
                Description = "Per-part-or-HeatModule array: name (string), temperature (deg C, CAN be literal string '+Inf'/'-Inf' -- real sentinel values, not errors), heatTolerance (deg C threshold, 400/1000/6000 for Low/Mid/High), isHeatShield (bool), exposedSurface ([PARTIAL] a length-like unit -- summed dx of drag-cull-surviving segments for that part, NOT a literal m^2 surface area)", RequestAs = "telemetry on ...,computed:heatParts" },
            new ProbeFieldInfo { Key = "aeroTorque", Namespace = "computed", Group = "aeroTorque", Unit = "N*m-equivalent (2D cross-product torque, sfs_physics_reference.md 2.5)",
                Description = "predicted torque about the world center of mass; null on failure", RequestAs = "telemetry on ...,computed:aeroTorque" },
            new ProbeFieldInfo { Key = "aeroAlphaDeg", Namespace = "computed", Group = "aeroTorque", Unit = "deg/s^2 -- ANGULAR ACCELERATION, not an angle",
                Description = "alphaPred * 57.29578 -- predicted angular acceleration from torque/inertia", RequestAs = "telemetry on ...,computed:aeroTorque" },
            new ProbeFieldInfo { Key = "rbInertia", Namespace = "computed", Group = "aeroTorque", Unit = "Unity rb2d.inertia units (kg*m^2-equivalent)",
                Description = "the actual moment of inertia used in the alpha calc", RequestAs = "telemetry on ...,computed:aeroTorque" },
            new ProbeFieldInfo { Key = "rbAngularDrag", Namespace = "computed", Group = "aeroTorque", Unit = "Unity rb2d.angularDrag units (dimensionless damping coefficient)",
                Description = "NEW v0.63.0: real Unity Rigidbody2D angularDrag, never read before -- AddForceAtPosition (real aero torque's mechanism) is genuine Unity physics and Unity's own solver applies this damping every tick; neither TryComputeAeroTorque's hand-derived alphaPred formula nor forward_sim.py's Python replica ever modeled it", RequestAs = "telemetry on ...,computed:aeroTorque" },
            new ProbeFieldInfo { Key = "gimbalOn", Namespace = "computed", Group = "gimbal", Unit = "bool",
                Description = "primary gimbaling engine's gimbalOn; null if no gimbaling engine exists at all. 'Primary' = first ON gimbaling engine, falling back to the first gimbaling engine found (even if off) if none are on (v0.56.1 fix)", RequestAs = "telemetry on ...,computed:gimbal" },
            new ProbeFieldInfo { Key = "gimbalThrottleOut", Namespace = "computed", Group = "gimbal", Unit = "0-1 float",
                Description = "primary gimbaling engine's throttle_Out", RequestAs = "telemetry on ...,computed:gimbal" },
            new ProbeFieldInfo { Key = "gimbalTurnAxisInput", Namespace = "computed", Group = "gimbal", Unit = "-1 to 1 float",
                Description = "primary gimbaling engine's turnAxis_Input", RequestAs = "telemetry on ...,computed:gimbal" },
            new ProbeFieldInfo { Key = "gimbalTime", Namespace = "computed", Group = "gimbal", Unit = "UNITLESS 0-1 fraction, NOT seconds or degrees",
                Description = "MoveModule.time -- chases targetTime linearly at rate 1/animationTime", RequestAs = "telemetry on ...,computed:gimbal" },
            new ProbeFieldInfo { Key = "gimbalTargetTime", Namespace = "computed", Group = "gimbal", Unit = "UNITLESS 0-1 fraction",
                Description = "MoveModule.targetTime -- the commanded target the animation is moving toward", RequestAs = "telemetry on ...,computed:gimbal" },
            new ProbeFieldInfo { Key = "torqueEffectiveLive", Namespace = "computed", Group = "torque", Unit = "same units as torqueEffectiveRaw (getforwardstartinfo)",
                Description = "LIVE per-tick sum of enabled TorqueModule.torque.Value (Rocket.GetTorque()'s real mechanism, via the existing SumEnabledTorque helper -- previously wired into full-mode telemetry only, never scoped). Added 2026-09-06 specifically to test whether a TorqueModule's torque expression is parametric on live state (e.g. throttle_Out) and therefore differs from the pre-ignition snapshot getforwardstartinfo captures.", RequestAs = "telemetry on ...,computed:torque" },
            new ProbeFieldInfo { Key = "parachuteTorque", Namespace = "computed", Group = "parachuteDrag", Unit = "N*m-equivalent",
                Description = "predicted torque including chute compounding; null on failure", RequestAs = "telemetry on ...,computed:parachuteDrag" },
            new ProbeFieldInfo { Key = "parachuteAlphaDeg", Namespace = "computed", Group = "parachuteDrag", Unit = "deg/s^2 -- ANGULAR ACCELERATION, NOT an angle despite the name",
                Description = "alphaPred * 57.29578. This is the exact key that motivated this registry's Unit field: the name looks like an angle but is an angular acceleration.", RequestAs = "telemetry on ...,computed:parachuteDrag" },
            new ProbeFieldInfo { Key = "parachuteChutesActive", Namespace = "computed", Group = "parachuteDrag", Unit = "count (int)",
                Description = "number of chutes with targetState in {1,2} (partial/full deploy) contributing this tick; 0 harmlessly reduces to the plain aero-torque case", RequestAs = "telemetry on ...,computed:parachuteDrag" },
            new ProbeFieldInfo { Key = "parachuteRbInertia", Namespace = "computed", Group = "parachuteDrag", Unit = "Unity rb2d.inertia units",
                Description = "same as aeroTorque's rbInertia", RequestAs = "telemetry on ...,computed:parachuteDrag" },
            new ProbeFieldInfo { Key = "parachuteForceX", Namespace = "computed", Group = "parachuteDrag", Unit = "force units (same scale as aeroTorque's underlying force)",
                Description = "total drag force x including chute contribution", RequestAs = "telemetry on ...,computed:parachuteDrag" },
            new ProbeFieldInfo { Key = "parachuteForceY", Namespace = "computed", Group = "parachuteDrag", Unit = "force units",
                Description = "total drag force y including chute contribution", RequestAs = "telemetry on ...,computed:parachuteDrag" },

            // ---- Namespace: truth (BuildTruthSample, full-schema, truth.jsonl) ----
            // Written every tick in FULL mode ('telemetry on' with no field list).
            // NOT reachable individually in SCOPED mode as a bare dot-path name --
            // scoped mode only recognizes computed:* and the literal string
            // "partCount" as special cases; every other name falls through to
            // ResolvePath, a third, different mechanism again (see script-condition
            // namespace above for the fourth). Do not assume a name here is usable
            // verbatim in a scoped field list.
            new ProbeFieldInfo { Key = "t", Namespace = "truth", Unit = "seconds", Description = "location.time",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "h", Namespace = "truth", Unit = "meters", Description = "location.Height",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "vv", Namespace = "truth", Unit = "m/s", Description = "location.VerticalVelocity",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "m", Namespace = "truth", Unit = "tonnes", Description = "rb2d.mass",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "rot", Namespace = "truth", Unit = "degrees", Description = "rb2d.rotation",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "angv", Namespace = "truth", Unit = "deg/s", Description = "rb2d.angularVelocity",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "px", Namespace = "truth", Unit = "meters, world/planet-centered, double precision",
                Description = "location.position.x (world frame, NOT rb2d's local-frame velocity)", RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "py", Namespace = "truth", Unit = "meters, world/planet-centered, double precision",
                Description = "location.position.y", RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "vx", Namespace = "truth", Unit = "m/s, world-frame", Description = "location.velocity.x",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "vy", Namespace = "truth", Unit = "m/s, world-frame", Description = "location.velocity.y",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "predApo", Namespace = "truth", Unit = "meters",
                Description = "predicted apoapsis from GetPredictedOrbit (via Physics.GetTrajectory(), only valid under live physics, not stale on-rails data)", RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "predPeri", Namespace = "truth", Unit = "meters", Description = "predicted periapsis",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "predEcc", Namespace = "truth", Unit = "unitless", Description = "predicted eccentricity",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "fuelByStage", Namespace = "truth", Unit = "array of {stage:int, fuel:tonnes, capacity:tonnes}",
                Description = "per-stage fuel remaining/capacity, summed across ResourceModules in each stage", RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "partCount", Namespace = "truth", Unit = "count (int)",
                Description = "from GetHeatState's Item1. In SCOPED telemetry mode this exact name IS also usable, via a dedicated special-case added in v0.55.0 -- see Fix note in mod_changelog.md.",
                RequestAs = "telemetry on (full mode) -- truth.jsonl; ALSO usable bare in scoped 'telemetry on <fields>' lists via a dedicated special-case (not ResolvePath)" },
            new ProbeFieldInfo { Key = "maxTemp", Namespace = "truth", Unit = "deg C",
                Description = "rocket-wide max part temperature from GetHeatState's Item2 (+-Infinity sentinels excluded before the max)", RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "dragArea", Namespace = "truth", Unit = "m^2-equivalent", Description = "same as computed:dragArea's dragArea",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "dragCopX", Namespace = "truth", Unit = "world-space meters", Description = "same as computed:dragArea's pre-Lerp CoP x",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "dragCopY", Namespace = "truth", Unit = "world-space meters", Description = "same as computed:dragArea's pre-Lerp CoP y",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "dragSurfaces", Namespace = "truth", Unit = "count", Description = "same as computed:dragArea",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "dragExposed", Namespace = "truth", Unit = "count", Description = "same as computed:dragArea",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "realAirTemp", Namespace = "truth", Unit = "deg C, or null",
                Description = "GetRealAirTemperature -- the game's own live AeroModule.GetTemperatureAndShockwave output (same helper the 'airtemp' command uses)", RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "heatParts", Namespace = "truth", Unit = "array of objects", Description = "same schema as computed:heatParts",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },
            new ProbeFieldInfo { Key = "body", Namespace = "truth", Unit = "string", Description = "current planet's codeName",
                RequestAs = "telemetry on (full mode, no field list) -- truth.jsonl" },

            // ---- Namespace: inputs (BuildInputsSample, full-schema only, inputs.jsonl) ----
            new ProbeFieldInfo { Key = "t", Namespace = "inputs", Unit = "seconds", Description = "tick time",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "fdt", Namespace = "inputs", Unit = "seconds", Description = "Time.fixedDeltaTime",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "m", Namespace = "inputs", Unit = "tonnes", Description = "rb2d.mass",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "thr", Namespace = "inputs", Unit = "0-1 float", Description = "throttle.throttlePercent",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "thrOn", Namespace = "inputs", Unit = "bool",
                Description = "throttle.throttleOn (master ignition). [KNOWN UNRELIABLE as a thrust indicator -- see high_level_checklist.md 'Tooling bugs'; prefer checking mass flatness.]",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "turnAxis", Namespace = "inputs", Unit = "-1 to 1 float (unclamped on direct write, see 'turn' command)",
                Description = "arrowkeys.turnAxis", RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "torque", Namespace = "inputs", Unit = "same units as TorqueModule.torque (sfs_physics_reference.md 2.4)",
                Description = "SumEnabledTorque -- sum of enabled TorqueModule.torque values", RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "rcsOn", Namespace = "inputs", Unit = "bool", Description = "arrowkeys.rcs",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "rcsFiring", Namespace = "inputs", Unit = "count (int)", Description = "CountFiringThrusters",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "directionalAxisX", Namespace = "inputs", Unit = "unitless direction component",
                Description = "Rocket.output_DirectionalAxis.x (confirmed NOT on arrowkeys -- a distinct field needed for RcsModule.DirectionThrust reconstruction)", RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "directionalAxisY", Namespace = "inputs", Unit = "unitless direction component",
                Description = "Rocket.output_DirectionalAxis.y", RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
            new ProbeFieldInfo { Key = "engines", Namespace = "inputs", Unit = "array of objects", Description = "same schema as computed:engines",
                RequestAs = "telemetry on (full mode, no field list) -- inputs.jsonl" },
        };

        static string RegistryToJson()
        {
            var sb = new StringBuilder();
            sb.Append("{\n  \"commands\":[");
            for (int i = 0; i < CommandRegistry.Length; i++)
            {
                var c = CommandRegistry[i];
                if (i > 0) sb.Append(",");
                sb.Append("{\"name\":").Append(Q(c.Name))
                  .Append(",\"syntax\":").Append(Q(c.Syntax))
                  .Append(",\"description\":").Append(Q(c.Description))
                  .Append(",\"category\":").Append(Q(c.Category))
                  .Append("}");
            }
            sb.Append("],\n  \"fields\":[");
            for (int i = 0; i < FieldRegistry.Length; i++)
            {
                var f = FieldRegistry[i];
                if (i > 0) sb.Append(",");
                sb.Append("{\"key\":").Append(Q(f.Key))
                  .Append(",\"namespace\":").Append(Q(f.Namespace))
                  .Append(",\"group\":").Append(Q(f.Group ?? ""))
                  .Append(",\"unit\":").Append(Q(f.Unit))
                  .Append(",\"description\":").Append(Q(f.Description))
                  .Append(",\"requestAs\":").Append(Q(f.RequestAs))
                  .Append("}");
            }
            sb.Append("]\n}");
            return sb.ToString();
        }

        // ---------- command dispatch ----------

        public static void Command(string line)
        {
            string[] a = line.Split(' ');
            string cmd = a[0].ToLowerInvariant();
            string arg = a.Length > 1 ? a[1] : null;

            switch (cmd)
            {
                case "ping":
                    ProbeMod.Result("pong  scene=" + SceneManager.GetActiveScene().name +
                                    "  rockets=" + RocketCount() +
                                    "  fixedDelta=" + Time.fixedDeltaTime.ToString("R") +
                                    "  gameVersion=" + Application.version +
                                    "  modVersion=" + ProbeMod.VersionString);
                    break;

                case "snapshot": DumpFlight("cmd"); break;
                case "world":    WroteWorld = false; DumpWorld("cmd"); break;
                case "menu":     DumpMenu("cmd"); break;

                case "dragareasweep":
                {
                    // 2026-09-06: reads the game's own REAL drag computation at a
                    // whole LIST of caller-chosen synthetic AoA values in one call,
                    // via TryComputeDragAreaAtAoA -- no actual flying through those
                    // angles required, works on a stationary craft. Built to replace
                    // the old approach (finite-differencing velocity from a real
                    // flight to empirically build an AoA table -- noisy, and only
                    // covers whatever angles the flight happened to pass through) --
                    // this gets the exact, noise-free, complete-coverage answer
                    // straight from the game for any angle requested. Argument: a
                    // comma-separated list of AoA degrees, e.g.
                    // "dragareasweep -90,-60,-30,0,30,60,90,120,150,180". No spaces.
                    object rSweep = ActiveRocket();
                    if (rSweep == null) { ProbeMod.Result("dragareasweep: no active rocket"); break; }
                    if (string.IsNullOrEmpty(arg)) { ProbeMod.Result("dragareasweep: needs a comma-separated list of AoA degrees, e.g. dragareasweep -90,-60,-30,0,30,60,90"); break; }

                    string[] aoaStrs = arg.Split(',');
                    var sweepResults = new List<string>();
                    for (int ai = 0; ai < aoaStrs.Length; ai++)
                    {
                        float aoaTarget;
                        if (!float.TryParse(aoaStrs[ai], out aoaTarget))
                        {
                            sweepResults.Add("{\"aoaDeg\":" + Q(aoaStrs[ai]) + ",\"error\":\"unparseable\"}");
                            continue;
                        }
                        float sweepDrag, sweepCopX, sweepCopY;
                        int sweepAllCount, sweepExposedCount;
                        bool sweepOk = TryComputeDragAreaAtAoA(rSweep, aoaTarget, out sweepDrag, out sweepCopX, out sweepCopY,
                            out sweepAllCount, out sweepExposedCount);
                        var ssb = new StringBuilder();
                        ssb.Append("{\"aoaDeg\":").Append(Num(aoaTarget));
                        ssb.Append(",\"dragArea\":").Append(sweepOk ? Num(sweepDrag) : "null");
                        ssb.Append(",\"dragCopX\":").Append(sweepOk ? Num(sweepCopX) : "null");
                        ssb.Append(",\"dragCopY\":").Append(sweepOk ? Num(sweepCopY) : "null");
                        ssb.Append(",\"allSurfaceCount\":").Append(sweepAllCount);
                        ssb.Append(",\"exposedSurfaceCount\":").Append(sweepExposedCount);
                        ssb.Append("}");
                        sweepResults.Add(ssb.ToString());
                    }

                    object rb2dSweep = Get(rSweep, "rb2d");
                    float thetaRealSweepDeg = ToF(Get(rb2dSweep, "rotation"));
                    var sweepOut = new StringBuilder();
                    sweepOut.Append("{\"realRotationDeg\":").Append(Num(thetaRealSweepDeg));
                    sweepOut.Append(",\"note\":\"dragCopX/Y are in the same velocity-aligned frame as computed:dragArea's dragCopX/Y -- NOT world/local frame, matching existing convention\"");
                    sweepOut.Append(",\"samples\":[").Append(string.Join(",", sweepResults.ToArray())).Append("]}");

                    string sweepJson = sweepOut.ToString();
                    File.WriteAllText(Path.Combine(ProbeMod.OutDir ?? ".", "sfs_probe_dragareasweep.json"), sweepJson);
                    ProbeMod.Result("dragareasweep: " + aoaStrs.Length + " angle(s) -> sfs_probe_dragareasweep.json");
                    break;
                }

                case "telemetry":
                {
                    // "telemetry on" -> default full-schema mode (unchanged).
                    // "telemetry on rb2d.mass,location.velocity.x,computed:dragArea"
                    //   -> scoped mode (v0.29): only these fields are recorded, one
                    //   truth.jsonl row per tick, no rebuild required to add/remove a
                    //   plain reflection path. "computed:NAME" dispatches to a
                    //   registered multi-field helper (see AppendComputedField) --
                    //   currently just "dragArea", more can be added there without
                    //   touching this parsing. "telemetry off" stops either mode.
                    //
                    // Optional auxiliary-trigger block (v0.53.0+), after a "|":
                    //   "telemetry on <fields> | <cond1>@<sec1>:<cmd1>; <cond2>@<sec2>:<cmd2>; ..."
                    //   General "what/when/how often" control: <fields> (before
                    //   the "|") is WHAT gets recorded every tick, same as
                    //   always; each "<cond>:<cmd>" entry after the "|" is WHEN
                    //   an on-demand command (gimbalinfo/rcsforce/terrain/etc.)
                    //   fires -- while <cond> holds true -- and the optional
                    //   "@<seconds>" is HOW OFTEN it re-fires while still true
                    //   (omit "@..." for a single shot). <cond> uses the exact
                    //   same grammar "script" steps already use
                    //   (TryParseCondition/GetScriptFieldValue/EvalOp), plus two
                    //   pseudo-fields added for this purpose: "gimbaling" (1/0)
                    //   and "rcsfiring" (live firing-thruster count). Omitting
                    //   the "|" block entirely, or writing "| auto", uses the
                    //   built-in default (see DefaultTelemetryTriggerSpec):
                    //   gimbalinfo while gimbaling, every 3s; rcsforce while
                    //   rcsfiring, every 2s; terrain once h<500 (then every 3s
                    //   while still under that height). "| none" disables all
                    //   auxiliary triggers entirely.
                    string[] parts3 = line.Split(new char[] { ' ' }, 3);
                    string mode = parts3.Length > 1 ? parts3[1] : null;
                    if (mode == "json")
                    {
                        // "telemetry json on" / "telemetry json off" (v0.59.0) --
                        // the independent per-part JSON rocket-state snapshot
                        // recorder (rocketstate.jsonl, ~1 Hz), separate from the
                        // truth/inputs telemetry above -- see StartJsonRecording/
                        // StopJsonRecording/SampleJson for the full design.
                        string jsonSubMode = parts3.Length > 2 ? parts3[2].Trim() : null;
                        if (jsonSubMode == "on") StartJsonRecording();
                        else if (jsonSubMode == "off" || string.IsNullOrEmpty(jsonSubMode)) StopJsonRecording();
                        else ProbeMod.Result("telemetry json: unrecognized mode '" + jsonSubMode +
                                              "' -- expected 'on' or 'off'. Command ignored.");
                    }
                    else if (mode == "on")
                    {
                        string[] fields = null;
                        string triggerSpec = null;
                        if (parts3.Length > 2 && !string.IsNullOrWhiteSpace(parts3[2]))
                        {
                            string rest = parts3[2];
                            int pipeIdx = rest.IndexOf('|');
                            string fieldsPart = (pipeIdx >= 0 ? rest.Substring(0, pipeIdx) : rest).Trim();
                            if (pipeIdx >= 0) triggerSpec = rest.Substring(pipeIdx + 1).Trim();
                            if (fieldsPart.Length > 0) fields = fieldsPart.Split(',');
                        }
                        StartRecording(fields, triggerSpec);
                    }
                    else if (mode == "off" || mode == null)
                    {
                        StopRecording();
                    }
                    else
                    {
                        // v0.58.0 fix: any non-"on" second word used to silently fall
                        // through to StopRecording() as if it meant "off" -- a real,
                        // confirmed bug (found 2026-09-04 via a separate live MCP
                        // session independently testing Checkpoint 3's fast-fail
                        // validation): sending the exact typo 'telemetry snapshot'
                        // (leading word 'telemetry' is a real command, so client-side
                        // leading-word validation can't catch this) silently stopped
                        // and archived an ACTIVE recording with no error surfaced --
                        // it read back as a normal success, not a mistake. Worse, if
                        // recording was already off, StopRecording() early-returns
                        // with NO result.txt line at all, producing a client-side
                        // timeout that looked like "nothing happened" when actually a
                        // malformed command silently reached this deep. Now any
                        // second word that isn't "on"/"off"/missing is a real,
                        // reported error -- no state changed either way.
                        ProbeMod.Result("telemetry: unrecognized mode '" + mode +
                                         "' -- expected 'on' or 'off' (omit for 'off'). " +
                                         "Command ignored, no recording state changed.");
                    }
                    break;
                }

                case "throttle":
                {
                    // Amount only. Does NOT touch master ignition (throttleOn) --
                    // that used to be a hidden side effect of this command and
                    // conflated "how much" with "start".
                    float v = float.Parse(arg, CultureInfo.InvariantCulture);
                    object r = ActiveRocket();
                    object th = Get(r, "throttle");
                    bool ok = SetWrapped(th, "throttlePercent", v);
                    ProbeMod.Result("throttle " + v + (ok ? " ok" : " FAILED (throttle obj=" + Name(th) + ")"));
                    break;
                }

                case "master":
                {
                    // Rocket-level master ignition switch ("start"). Independent
                    // of both throttle amount and per-engine activation.
                    bool on = (arg == "on");
                    object r = ActiveRocket();
                    object th = Get(r, "throttle");
                    bool ok = SetWrapped(th, "throttleOn", on);
                    ProbeMod.Result("master " + (on ? "ON" : "OFF") + (ok ? " ok" : " FAILED"));
                    break;
                }

                case "diag":
                {
                    // Walks the SAME code path ignite/torque/fuel use (ModuleValues),
                    // per part, so a count mismatch against the snapshot's own Dump()
                    // path can be traced to whichever one is wrong.
                    object r = ActiveRocket();
                    object holder = Get(r, "partHolder");
                    object parts = Get(holder, "parts");
                    var en = parts as System.Collections.IEnumerable;
                    var lines = new List<string>();
                    int partIdx = 0;
                    if (en != null)
                    {
                        foreach (object part in en)
                        {
                            partIdx++;
                            string pname = "?";
                            try { pname = (string)Get(Get(part, "displayName"), "TranslatableName"); } catch { }
                            int engCount = 0;
                            foreach (object mv in ModuleValues(part))
                                if (mv.GetType().Name == "EngineModule") engCount++;
                            lines.Add(partIdx + ":" + pname + "=" + engCount);
                        }
                    }
                    ProbeMod.Result("diag parts=" + partIdx + "  " + string.Join(" ", lines.ToArray()));
                    break;
                }

                case "autostop":
                    // "autostop on" / "autostop turnover" -> ascent-phase stop
                    // "autostop land"                     -> descent-phase stop
                    // "autostop off"                      -> disarm
                    if (arg == "off")
                    {
                        Probe.AutoStop = false;
                        ProbeMod.Result("autostop OFF");
                    }
                    else
                    {
                        Probe.SetAutoStopMode(arg == "land" ? "land" : "turnover");
                        ProbeMod.Result("autostop ON mode=" + (arg == "land" ? "land" : "turnover"));
                    }
                    break;

                case "ignite":
                {
                    // Per-engine activation ("which engines"). Normally done by
                    // staging; this sets EngineModule.engineOn directly on every
                    // engine found, independent of throttle amount and master.
                    object r = ActiveRocket();
                    object holder = Get(r, "partHolder");
                    object parts = Get(holder, "parts");
                    var en = parts as System.Collections.IEnumerable;
                    int lit = 0;
                    if (en != null)
                    {
                        foreach (object part in en)
                        {
                            foreach (object mv in ModuleValues(part))
                            {
                                if (mv.GetType().Name != "EngineModule") continue;
                                if (SetWrapped(mv, "engineOn", true)) lit++;
                            }
                        }
                    }
                    ProbeMod.Result("ignite: " + lit + " engine(s) armed");
                    break;
                }

                case "revert":
                {
                    object gm = FindComponent("SFS.World.GameManager");
                    Invoke(gm, "RevertToLaunch", new object[] { false });
                    ProbeMod.Result("revert requested");
                    break;
                }

                case "achievements":
                {
                    // Confirmed via IL: what the wiki calls "achievements" is
                    // internally SFS.Logs.Challenge -- plain public fields, no
                    // wrapper types. Full catalog lives at the static
                    // SFS.Base.worldBase.challengesArray (Challenge[]); which of
                    // those are done for the CURRENT rocket/save comes from
                    // Rocket.stats.challengeRecorder.GetCompleteChallenges(), a
                    // real public method, no reflection hacks needed for that
                    // part. Not a Steamworks achievement -- purely in-game state.
                    object baseType = FindType("SFS.Base");
                    object worldBase = Get(baseType, "worldBase");
                    object challengesArr = Get(worldBase, "challengesArray");
                    var enAll = challengesArr as System.Collections.IEnumerable;

                    var completedIds = new HashSet<string>();
                    object rr = ActiveRocket();
                    if (rr != null)
                    {
                        object stats = Get(rr, "stats");
                        object cr = Get(stats, "challengeRecorder");
                        object completeSet = InvokeReturn(cr, "GetCompleteChallenges", new object[0]);
                        var enComplete = completeSet as System.Collections.IEnumerable;
                        if (enComplete != null)
                            foreach (object c in enComplete)
                            {
                                string cid = Get(c, "id") as string;
                                if (cid != null) completedIds.Add(cid);
                            }
                    }

                    var asb = new StringBuilder();
                    asb.Append("{\"challenges\":[");
                    bool afirst = true;
                    int acount = 0;
                    if (enAll != null)
                    {
                        foreach (object c in enAll)
                        {
                            if (c == null) continue;
                            string id = Get(c, "id") as string;
                            object titleFn = Get(c, "title");
                            object descFn = Get(c, "description");
                            string title = null, desc = null;
                            try { if (titleFn != null) title = ((Func<string>)titleFn)(); } catch { }
                            try { if (descFn != null) desc = ((Func<string>)descFn)(); } catch { }
                            object owner = Get(c, "owner");
                            string planetName = owner != null ? (Get(owner, "codeName") as string) : null;
                            object diff = Get(c, "difficulty");
                            bool returnSafely = ToB(Get(c, "returnSafely"));
                            object stepsObj = Get(c, "steps");
                            var stepsColl = stepsObj as System.Collections.ICollection;
                            int stepCount = stepsColl != null ? stepsColl.Count : -1;
                            bool completed = id != null && completedIds.Contains(id);

                            if (!afirst) asb.Append(",");
                            afirst = false;
                            acount++;
                            asb.Append("{\"id\":").Append(Q(id));
                            asb.Append(",\"title\":").Append(Q(title));
                            asb.Append(",\"description\":").Append(Q(desc));
                            asb.Append(",\"planet\":").Append(Q(planetName));
                            asb.Append(",\"difficulty\":").Append(Q(diff != null ? diff.ToString() : null));
                            asb.Append(",\"returnSafely\":").Append(returnSafely ? "true" : "false");
                            asb.Append(",\"stepCount\":").Append(stepCount);
                            asb.Append(",\"completed\":").Append(completed ? "true" : "false");
                            asb.Append("}");
                        }
                    }
                    asb.Append("],\"completedCount\":").Append(completedIds.Count);
                    asb.Append(",\"totalCount\":").Append(acount);
                    asb.Append("}");
                    Write("sfs_probe_achievements.json", asb, "achievements dump");
                    ProbeMod.Result("achievements: " + completedIds.Count + "/" + acount + " complete -> sfs_probe_achievements.json");
                    break;
                }

                case "geometry":
                {
                    // Reads whatever GeometryCapture has captured so far via the
                    // Harmony postfix on Part.InitializePart() -- passive capture,
                    // this command never triggers init itself. See the
                    // GeometryCapture/GeometryPatches classes below for how/why.
                    object r = ActiveRocket();
                    object holder = Get(r, "partHolder");
                    object parts = Get(holder, "parts");
                    var en = parts as System.Collections.IEnumerable;
                    var items = new List<string>();
                    int withGeom = 0, total = 0;
                    if (en != null)
                    {
                        foreach (object part in en)
                        {
                            total++;
                            string pname = "?";
                            try { pname = (string)Get(Get(part, "displayName"), "TranslatableName"); } catch { }

                            GeometryCapture.Captured cap;
                            bool has = GeometryCapture.TryGet(part, out cap);
                            if (has) withGeom++;

                            var gsb = new StringBuilder();
                            gsb.Append("{\"name\":").Append(Q(pname));
                            gsb.Append(",\"hasGeometry\":").Append(has ? "true" : "false");
                            if (has)
                            {
                                gsb.Append(",\"captureCount\":").Append(cap.CaptureCount);
                                gsb.Append(",\"loops\":[");
                                for (int i = 0; i < cap.Loops.Count; i++)
                                {
                                    if (i > 0) gsb.Append(",");
                                    gsb.Append("{\"loop\":").Append(cap.LoopFlags[i] ? "true" : "false");
                                    gsb.Append(",\"points\":[");
                                    Vector2[] pts = cap.Loops[i];
                                    for (int j = 0; j < pts.Length; j++)
                                    {
                                        if (j > 0) gsb.Append(",");
                                        gsb.Append("[").Append(pts[j].x.ToString("R"))
                                          .Append(",").Append(pts[j].y.ToString("R")).Append("]");
                                    }
                                    gsb.Append("]}");
                                }
                                gsb.Append("]");
                            }
                            gsb.Append("}");
                            items.Add(gsb.ToString());
                        }
                    }
                    var geomOutSb = new StringBuilder();
                    geomOutSb.Append("{\"parts\":[").Append(string.Join(",", items.ToArray()));
                    geomOutSb.Append("],\"withGeometry\":").Append(withGeom).Append(",\"total\":").Append(total).Append("}");
                    Write("sfs_probe_geometry.json", geomOutSb, "geometry dump");
                    ProbeMod.Result("geometry: " + withGeom + "/" + total + " parts have captured geometry -> sfs_probe_geometry.json");
                    break;
                }

                case "dragarea":
                {
                    // Harmony-free path (2026-08-27): dragArea and center-of-pressure
                    // are directly callable via plain reflection on methods the game
                    // already calls every FixedUpdate -- no geometry capture, no
                    // Harmony patch needed at all (that path was fully abandoned; see
                    // GeometryPatches/GeometryCapture below, kept only for reference).
                    // Confirmed via IL, not guessed:
                    //   - Aero_Rocket.GetDragSurfaces(Matrix2x2) -- 1-arg INSTANCE
                    //     overload, callable on rocket.aero directly. A 2-arg static
                    //     overload shares the name, so plain GetMethod(name) would throw
                    //     AmbiguousMatchException -- resolved below with explicit types.
                    //   - AeroModule.GetExposedSurfaces(List<Surface>) -- static.
                    //   - AeroModule.CalculateDragForce(List<Surface>) -- static, returns
                    //     ValueTuple<float,Vector2> = (drag, centerOfDrag), confirmed via
                    //     the method's own TupleElementNamesAttribute metadata. THIS is
                    //     the real dragArea value, straight from the game's own calc.
                    //   - Rotation input is NOT identity -- traced from the real call
                    //     site inside AeroModule.FixedUpdate()'s own IL body:
                    //     rotationInput = -(velocity.AngleRadians - PI/2).
                    object r = ActiveRocket();
                    if (r == null) { ProbeMod.Result("dragarea: no active rocket"); break; }
                    object aero = Get(r, "aero");
                    if (aero == null) { ProbeMod.Result("dragarea: rocket.aero is null"); break; }

                    Type matrixType = FindType("Matrix2x2");
                    Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
                    if (matrixType == null || aeroModuleType == null)
                    {
                        ProbeMod.Result("dragarea: FAILED to resolve Matrix2x2 or AeroModule type");
                        break;
                    }

                    object dloc = Unwrap(Get(r, "location"));
                    object velocity = GetWrapped(dloc, "velocity");
                    double velocityAngle = ToD(Get(velocity, "AngleRadians"));
                    float rotationInput = (float)(-(velocityAngle - Math.PI / 2.0));
                    object matrix = InvokeStatic(matrixType, "Angle", new Type[] { typeof(float) }, new object[] { rotationInput });
                    if (matrix == null) { ProbeMod.Result("dragarea: Matrix2x2.Angle FAILED"); break; }

                    MethodInfo getDragSurfaces = aero.GetType().GetMethod("GetDragSurfaces",
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                        null, new Type[] { matrixType }, null);
                    if (getDragSurfaces == null)
                    {
                        ProbeMod.Result("dragarea: couldn't resolve the 1-arg GetDragSurfaces overload");
                        break;
                    }

                    object allSurfaces;
                    try { allSurfaces = getDragSurfaces.Invoke(aero, new object[] { matrix }); }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        ProbeMod.Result("dragarea: GetDragSurfaces threw: " + msg);
                        break;
                    }

                    var allEn = allSurfaces as System.Collections.IEnumerable;
                    int allCount = 0;
                    if (allEn != null) foreach (object s in allEn) allCount++;

                    object exposedSurfaces = allSurfaces == null ? null :
                        InvokeStatic(aeroModuleType, "GetExposedSurfaces",
                            new Type[] { allSurfaces.GetType() }, new object[] { allSurfaces });
                    var exposedEn = exposedSurfaces as System.Collections.IEnumerable;
                    int exposedCount = 0;
                    if (exposedEn != null) foreach (object s in exposedEn) exposedCount++;

                    var dsb = new StringBuilder();
                    dsb.Append("{\"allSurfaceCount\":").Append(allCount);
                    dsb.Append(",\"exposedSurfaceCount\":").Append(exposedCount);

                    dsb.Append(",\"sampleSegments\":[");
                    if (allEn != null)
                    {
                        int shown = 0; bool firstSeg = true;
                        foreach (object s in allEn)
                        {
                            if (shown >= 10) break;
                            object segLine = Get(s, "line");
                            object start = Get(segLine, "start");
                            object end = Get(segLine, "end");
                            if (!(start is Vector2) || !(end is Vector2)) continue;
                            Vector2 sp = (Vector2)start, ep = (Vector2)end;
                            if (!firstSeg) dsb.Append(",");
                            firstSeg = false;
                            dsb.Append("{\"start\":[").Append(sp.x.ToString("R")).Append(",").Append(sp.y.ToString("R")).Append("]");
                            dsb.Append(",\"end\":[").Append(ep.x.ToString("R")).Append(",").Append(ep.y.ToString("R")).Append("]}");
                            shown++;
                        }
                    }
                    dsb.Append("]");

                    if (exposedSurfaces != null)
                    {
                        MethodInfo calcDrag = aeroModuleType.GetMethod("CalculateDragForce",
                            BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static,
                            null, new Type[] { exposedSurfaces.GetType() }, null);
                        if (calcDrag != null)
                        {
                            try
                            {
                                object tupleObj = calcDrag.Invoke(null, new object[] { exposedSurfaces });
                                var tuple = (System.ValueTuple<float, Vector2>)tupleObj;
                                dsb.Append(",\"calculateDragForce\":{\"item1\":").Append(tuple.Item1.ToString("R"));
                                dsb.Append(",\"item2\":[").Append(tuple.Item2.x.ToString("R"))
                                   .Append(",").Append(tuple.Item2.y.ToString("R")).Append("]}");
                            }
                            catch (Exception e)
                            {
                                string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                                dsb.Append(",\"calculateDragForceError\":").Append(Q(msg));
                            }
                        }
                        else { dsb.Append(",\"calculateDragForceError\":\"couldn't resolve CalculateDragForce overload\""); }
                    }

                    dsb.Append("}");
                    Write("sfs_probe_dragarea.json", dsb, "dragarea dump");
                    ProbeMod.Result("dragarea: all=" + allCount + " exposed=" + exposedCount + " -> sfs_probe_dragarea.json");
                    break;
                }

                case "loadblueprint":
                {
                    // Loads a rocket design bypassing the editor UI entirely.
                    // Reads Blueprint.txt-format JSON from an ARBITRARY file path
                    // (does NOT require the file to live inside the game's own
                    // Saving/Blueprints/ folder -- reads it directly with plain
                    // File I/O), deserializes via the game's own
                    // JsonWrapper.FromJson<Blueprint> (generic, needs
                    // MakeGenericMethod), then calls the confirmed public-static
                    // RocketManager.SpawnBlueprint. Confirmed via IL reading
                    // (docs/sfs_source_reference.md D5.1/D5.4/D5.5), matches the
                    // real on-disk format found in an actual saved blueprint.
                    //
                    // *** DO NOT CALL THIS DURING A LIVE FLIGHT AS ROUTINE USE. ***
                    // Confirmed 2026-08-29: SpawnBlueprint's FIRST action is
                    // WorldView.main.SetViewLocation(LaunchPadLocation) -- moving
                    // the camera to the pad. That is the signature of a ONE-TIME
                    // internal Build-to-World launch-transition primitive (the
                    // actual "Launch" button's mechanism), not a general spawn
                    // tool the game itself ever calls mid-flight or repeatedly.
                    // Calling it during an active flight materializes a fully-
                    // fueled part with none of a real launch's cost/sequence/
                    // achievement tracking -- functionally cheating, and outside
                    // any state the game was designed to handle repeatedly. The
                    // one successful live test (2026-08-28) proved the reflection
                    // mechanism works; it is NOT a green light for routine use.
                    // For loading a design into the editor (a legitimate,
                    // routinely-repeatable operation), use "loadblueprintbuild"
                    // below instead -- that's the real "Load Blueprint" button.
                    //
                    // SCENE REQUIREMENT CORRECTED (2026-08-29, first live test):
                    // originally gated on Build_PC (an untested assumption --
                    // "should be in the design screen"). First live call from
                    // Build_PC threw NullReferenceException; reading
                    // SpawnBlueprint's actual IL body showed why -- its very
                    // FIRST instructions are
                    // WorldView.main.SetViewLocation(SpaceCenterData.
                    // LaunchPadLocation), dereferencing the static WorldView.main
                    // singleton before touching a single part. That singleton is
                    // populated in World_PC (a loaded flight/world), not Build_PC
                    // (the editor) -- so the gate needed to be the opposite of
                    // what was first guessed. Confirmed by retesting from
                    // World_PC -- the mechanism itself genuinely works, it's the
                    // wisdom of using it live that's now in question (see above).
                    //
                    // Path can contain spaces (this project's own folder is
                    // literally named "SFS AI") -- split into exactly 2 pieces,
                    // same pattern as the "telemetry" case above, NOT the
                    // single-word `arg` every other case uses.
                    string[] parts2 = line.Split(new char[] { ' ' }, 2);
                    string path = parts2.Length > 1 ? parts2[1].Trim() : null;

                    if (string.IsNullOrEmpty(path))
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=no_path");
                        break;
                    }

                    string scene = SceneManager.GetActiveScene().name;
                    if (scene != "World_PC")
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=not_in_world scene=" + scene);
                        break;
                    }

                    if (!File.Exists(path))
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=file_not_found path=" + path);
                        break;
                    }

                    string json;
                    try { json = File.ReadAllText(path); }
                    catch (Exception e)
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=read_error " + e.Message);
                        break;
                    }

                    Type blueprintType = FindType("SFS.Builds.Blueprint");
                    Type jsonWrapperType = FindType("SFS.Parsers.Json.JsonWrapper");
                    Type rocketManagerType = FindType("SFS.World.RocketManager");
                    if (blueprintType == null || jsonWrapperType == null || rocketManagerType == null)
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=type_resolution blueprint=" + (blueprintType != null) +
                                         " jsonWrapper=" + (jsonWrapperType != null) + " rocketManager=" + (rocketManagerType != null));
                        break;
                    }

                    MethodInfo fromJsonGeneric = jsonWrapperType.GetMethod("FromJson",
                        BindingFlags.Public | BindingFlags.Static);
                    if (fromJsonGeneric == null)
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=fromjson_method_not_found");
                        break;
                    }
                    MethodInfo fromJson = fromJsonGeneric.MakeGenericMethod(blueprintType);

                    object blueprint;
                    try { blueprint = fromJson.Invoke(null, new object[] { json }); }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        ProbeMod.Result("loadblueprint: FAILED reason=deserialize_error " + msg);
                        break;
                    }
                    if (blueprint == null)
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=deserialize_null");
                        break;
                    }

                    MethodInfo spawnMethod = rocketManagerType.GetMethod("SpawnBlueprint",
                        BindingFlags.Public | BindingFlags.Static, null, new Type[] { blueprintType }, null);
                    if (spawnMethod == null)
                    {
                        ProbeMod.Result("loadblueprint: FAILED reason=spawn_method_not_found");
                        break;
                    }

                    try { spawnMethod.Invoke(null, new object[] { blueprint }); }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        ProbeMod.Result("loadblueprint: FAILED reason=spawn_exception " + msg);
                        break;
                    }

                    ProbeMod.Result("loadblueprint: OK path=" + path);
                    break;
                }

                case "loadblueprintbuild":
                {
                    // Loads a blueprint into the BUILD/EDITOR context,
                    // REPLACING the current design -- this is the actual
                    // mechanism behind the game's own "Load Blueprint" button,
                    // confirmed by reading BuildState.LoadBlueprint's real IL
                    // body (2026-08-29). Distinct from 'loadblueprint' above
                    // (RocketManager.SpawnBlueprint, spawns an ADDITIONAL live
                    // physics rocket into an active World_PC flight) -- this
                    // one operates entirely within BuildState/BuildMenus/
                    // BuildOrientation/BuildGrid (all editor-scoped types),
                    // calls BuildState.Clear() first (hence "replaces"), and
                    // has NO WorldView dependency at all -- correctly requires
                    // Build_PC, not World_PC, the opposite of 'loadblueprint'.
                    //
                    // LoadBlueprint(Blueprint, I_MsgLogger, bool autoCenterParts,
                    // bool applyUndo, Vector2 offset, Action onLoaded) -- public
                    // instance method @94166. Passes autoCenterParts=true,
                    // applyUndo=true (matches normal UI load behavior, integrates
                    // with editor undo history), offset=Vector2.zero, onLoaded=null.
                    string[] parts4 = line.Split(new char[] { ' ' }, 2);
                    string pathBuild = parts4.Length > 1 ? parts4[1].Trim() : null;

                    if (string.IsNullOrEmpty(pathBuild))
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=no_path");
                        break;
                    }

                    string sceneBuild = SceneManager.GetActiveScene().name;
                    if (sceneBuild != "Build_PC")
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=not_in_build scene=" + sceneBuild);
                        break;
                    }

                    if (!File.Exists(pathBuild))
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=file_not_found path=" + pathBuild);
                        break;
                    }

                    string jsonBuild;
                    try { jsonBuild = File.ReadAllText(pathBuild); }
                    catch (Exception e)
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=read_error " + e.Message);
                        break;
                    }

                    Type blueprintTypeBuild = FindType("SFS.Builds.Blueprint");
                    Type jsonWrapperTypeBuild = FindType("SFS.Parsers.Json.JsonWrapper");
                    Type buildStateType = FindType("SFS.Builds.BuildState");
                    Type msgLoggerType = FindType("SFS.I_MsgLogger");
                    if (blueprintTypeBuild == null || jsonWrapperTypeBuild == null ||
                        buildStateType == null || msgLoggerType == null)
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=type_resolution blueprint=" +
                            (blueprintTypeBuild != null) + " jsonWrapper=" + (jsonWrapperTypeBuild != null) +
                            " buildState=" + (buildStateType != null) + " msgLogger=" + (msgLoggerType != null));
                        break;
                    }

                    MethodInfo fromJsonGenericBuild = jsonWrapperTypeBuild.GetMethod("FromJson",
                        BindingFlags.Public | BindingFlags.Static);
                    if (fromJsonGenericBuild == null)
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=fromjson_method_not_found");
                        break;
                    }
                    MethodInfo fromJsonBuild = fromJsonGenericBuild.MakeGenericMethod(blueprintTypeBuild);

                    object blueprintBuild;
                    try { blueprintBuild = fromJsonBuild.Invoke(null, new object[] { jsonBuild }); }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=deserialize_error " + msg);
                        break;
                    }
                    if (blueprintBuild == null)
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=deserialize_null");
                        break;
                    }

                    // PRE-VALIDATION (2026-08-29, Step 1.5 audit finding 5/6):
                    // BuildState.LoadBlueprint's own body calls Clear(applyUndo)
                    // FIRST, before any part-spawning/validation happens -- so if
                    // spawning throws afterward, the CURRENT DESIGN IS ALREADY
                    // GONE by the time we'd see reason=load_exception. Can't
                    // change that ordering (it's inside the game's own method),
                    // but the single most likely cause -- a part name that
                    // doesn't match the real catalog -- is checkable BEFORE
                    // calling LoadBlueprint at all, while the current design is
                    // still intact. PartSave.name confirmed via IL as the real
                    // field (JSON-aliased to "n").
                    object partsField = Get(blueprintBuild, "parts");
                    var partsEnumForValidation = partsField as System.Collections.IEnumerable;
                    if (partsEnumForValidation != null)
                    {
                        object catalogObj = Get(FindComponent("SFS.Parts.PartsLoader"), "parts");
                        var catalogEn = catalogObj as System.Collections.IEnumerable;
                        var catalogNames = new HashSet<string>();
                        if (catalogEn != null)
                            foreach (object kv in catalogEn)
                            {
                                string k = Get(kv, "Key") as string;
                                if (k != null) catalogNames.Add(k);
                            }
                        if (catalogNames.Count > 0)
                        {
                            var badNames = new List<string>();
                            foreach (object ps in partsEnumForValidation)
                            {
                                string pn = Get(ps, "name") as string;
                                if (pn != null && !catalogNames.Contains(pn) && !badNames.Contains(pn))
                                    badNames.Add(pn);
                            }
                            if (badNames.Count > 0)
                            {
                                ProbeMod.Result("loadblueprintbuild: FAILED reason=unknown_part_names parts=" +
                                                 string.Join(",", badNames.ToArray()) +
                                                 " (current design NOT modified -- caught before Clear())");
                                break;
                            }
                        }
                    }

                    object buildState = FindComponent("SFS.Builds.BuildState");
                    if (buildState == null)
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=buildstate_not_found");
                        break;
                    }

                    // Real I_MsgLogger implementation, same one the normal UI
                    // uses -- matches what a human clicking "Load" would supply.
                    // Not strictly confirmed required (LoadBlueprint's own body
                    // only passes logger through, never calls .Log() directly
                    // itself), but safer than guessing null is tolerated deeper
                    // in the private SpawnBlueprint call it feeds into.
                    object logger = FindComponent("SFS.UI.MsgDrawer");

                    MethodInfo loadMethod = buildStateType.GetMethod("LoadBlueprint",
                        BindingFlags.Public | BindingFlags.Instance, null,
                        new Type[] { blueprintTypeBuild, msgLoggerType, typeof(bool), typeof(bool),
                                     typeof(Vector2), typeof(Action) },
                        null);
                    if (loadMethod == null)
                    {
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=load_method_not_found");
                        break;
                    }

                    try
                    {
                        loadMethod.Invoke(buildState, new object[] {
                            blueprintBuild, logger, true, true, Vector2.zero, null
                        });
                    }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        // Part-name pre-validation above catches the most likely
                        // cause, but LoadBlueprint's own body still calls Clear()
                        // BEFORE any other failure mode here could be detected
                        // (e.g. DLC/ownership rejection, a malformed variable) --
                        // so a load_exception past pre-validation may mean the
                        // previous design IS gone, not that "nothing happened."
                        ProbeMod.Result("loadblueprintbuild: FAILED reason=load_exception " + msg +
                                         " (WARNING: BuildState.Clear() runs before this point in the game's " +
                                         "own LoadBlueprint body -- the previous design may already be gone)");
                        break;
                    }

                    ProbeMod.Result("loadblueprintbuild: OK path=" + pathBuild);
                    break;
                }

                case "getplacedmagnets":
                {
                    // Reads REAL MagnetModule.points from the ACTUALLY PLACED
                    // parts currently in the editor (BuildState.buildGrid.
                    // activeGrid.partsHolder.parts -- the same live List<Part>
                    // GetBlueprint() itself reads from), not the bare catalog
                    // prefabs 'getparts' checks. Built 2026-08-29 after 'getparts'
                    // came back null for magnet data on all three tested catalog
                    // parts (Capsule/Fuel Tank/Engine Hawk) -- same class of gap
                    // as surfaceGeometry needing an actual placed instance, not a
                    // bare prefab, though unlike that case this doesn't need
                    // InitializePart() at all (Point.position is a plain field).
                    //
                    // Requires Build_PC with at least one part already placed.
                    Type buildStateTypeM = FindType("SFS.Builds.BuildState");
                    if (buildStateTypeM == null)
                    {
                        ProbeMod.Result("getplacedmagnets: FAILED reason=type_resolution");
                        break;
                    }
                    object buildStateMainM = Get(buildStateTypeM, "main");
                    if (buildStateMainM == null)
                    {
                        ProbeMod.Result("getplacedmagnets: FAILED reason=no_buildstate_main");
                        break;
                    }
                    object buildGrid = Get(buildStateMainM, "buildGrid");
                    object activeGrid = Get(buildGrid, "activeGrid");
                    object partsHolder = Get(activeGrid, "partsHolder");
                    object placedParts = Get(partsHolder, "parts");
                    var placedEn = placedParts as System.Collections.IEnumerable;
                    if (placedEn == null)
                    {
                        ProbeMod.Result("getplacedmagnets: FAILED reason=no_placed_parts");
                        break;
                    }

                    var placedItems = new List<string>();
                    int placedCount = 0;
                    foreach (object part in placedEn)
                    {
                        if (part == null) continue;
                        placedCount++;
                        string pname = "?";
                        try { pname = (string)Get(Get(part, "displayName"), "TranslatableName"); } catch { }
                        var psb = new StringBuilder();
                        psb.Append("{\"part\":").Append(Q(pname));
                        psb.Append(",\"magnetPoints\":").Append(DumpMagnetPoints(part));
                        psb.Append("}");
                        placedItems.Add(psb.ToString());
                    }

                    var pOutSb = new StringBuilder();
                    pOutSb.Append("{\"placedParts\":[").Append(string.Join(",", placedItems.ToArray()));
                    pOutSb.Append("],\"total\":").Append(placedCount).Append("}");
                    Write("sfs_probe_placed_magnets.json", pOutSb, "getplacedmagnets total=" + placedCount);
                    ProbeMod.Result("getplacedmagnets: " + placedCount + " placed parts -> sfs_probe_placed_magnets.json");
                    break;
                }

                case "dumpblueprint":
                {
                    // Reads the CURRENT editor design as a real Blueprint object
                    // via BuildState.main.GetBlueprint(bool) -- the game's own
                    // "get current design as data" method, confirmed via IL (real
                    // call sites @91631/94065/94082, same file the LoadBlueprint
                    // body was read from). Serializes via the same
                    // JsonWrapper.ToJson used elsewhere. This is how a real,
                    // verified parts-properties table gets built instead of
                    // guessed: place a part in the editor, dump the resulting
                    // blueprint, read its REAL NUMBER_VARIABLES/position -- not
                    // what was asked for, but what the game actually produced.
                    Type buildStateType = FindType("SFS.Builds.BuildState");
                    if (buildStateType == null)
                    {
                        ProbeMod.Result("dumpblueprint: FAILED reason=type_resolution");
                        break;
                    }
                    object buildStateMain = Get(buildStateType, "main");
                    if (buildStateMain == null)
                    {
                        ProbeMod.Result("dumpblueprint: FAILED reason=no_buildstate_main");
                        break;
                    }
                    MethodInfo getBp = buildStateType.GetMethod("GetBlueprint",
                        BindingFlags.Public | BindingFlags.Instance, null, new Type[] { typeof(bool) }, null);
                    if (getBp == null)
                    {
                        ProbeMod.Result("dumpblueprint: FAILED reason=getblueprint_not_found");
                        break;
                    }
                    object bp;
                    try { bp = getBp.Invoke(buildStateMain, new object[] { true }); }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        ProbeMod.Result("dumpblueprint: FAILED reason=getblueprint_exception " + msg);
                        break;
                    }
                    if (bp == null)
                    {
                        ProbeMod.Result("dumpblueprint: FAILED reason=blueprint_null");
                        break;
                    }

                    Type jsonWrapperType = FindType("SFS.Parsers.Json.JsonWrapper");
                    if (jsonWrapperType == null)
                    {
                        ProbeMod.Result("dumpblueprint: FAILED reason=jsonwrapper_type_not_found");
                        break;
                    }
                    MethodInfo toJson = jsonWrapperType.GetMethod("ToJson",
                        BindingFlags.Public | BindingFlags.Static, null,
                        new Type[] { typeof(object), typeof(bool) }, null);
                    if (toJson == null)
                    {
                        ProbeMod.Result("dumpblueprint: FAILED reason=tojson_method_not_found");
                        break;
                    }
                    string json;
                    try { json = (string)toJson.Invoke(null, new object[] { bp, true }); }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        ProbeMod.Result("dumpblueprint: FAILED reason=tojson_exception " + msg);
                        break;
                    }

                    try { File.WriteAllText(Path.Combine(ProbeMod.OutDir ?? ".", "sfs_probe_current_blueprint.json"), json); }
                    catch (Exception e)
                    {
                        ProbeMod.Result("dumpblueprint: FAILED reason=write_error " + e.Message);
                        break;
                    }
                    ProbeMod.Result("dumpblueprint: OK bytes=" + json.Length + " -> sfs_probe_current_blueprint.json");
                    break;
                }

                case "getparts":
                {
                    // Full parts-catalog index: real name + mass + centerOfMass +
                    // REAL parametric variable names/values, properly extracted
                    // past the generic Dump()'s depth-3 cutoff (which only shows
                    // the bare type name "VariableSave" for each entry, not its
                    // actual contents -- the same class of problem already fixed
                    // once for surfaceGeometry). This is what a real "why did the
                    // Fuel Tank spawn tiny" answer needs: the tank's real
                    // configurable variables (height/radius/etc, whatever they're
                    // actually called), not a guess.
                    //
                    // ALSO dumps PartsLoader.partVariants (v0.35.1) -- a SEPARATE
                    // Dictionary<string,VariantRef>, confirmed via IL, that
                    // "getparts"'s first version never read at all. Found because
                    // a live in-game count (57+, manually counted, not even
                    // through all tabs) didn't match the 56 total from 'parts'
                    // alone -- the build menu almost certainly shows variants as
                    // their own selectable tiles too. VariantRef's exact field
                    // schema wasn't independently confirmed via IL before this was
                    // written, so its fields are read generically (whatever
                    // they're actually called), same as VariableSave above.
                    //
                    // DELIBERATELY NOT part of the automatic on-load 'menu' dump
                    // (DumpMenu, unchanged, still runs on every scene load) --
                    // this is heavier and command-gated on purpose, so a normal
                    // game launch/reload stays fast. Only runs when explicitly
                    // requested.
                    object partsObj = Get(FindComponent("SFS.Parts.PartsLoader"), "parts");
                    var pen = partsObj as System.Collections.IEnumerable;
                    if (pen == null) { ProbeMod.Result("getparts: FAILED reason=no_parts_catalog"); break; }

                    var items = new List<string>();
                    int total = 0;
                    foreach (object kv in pen)
                    {
                        object part = Get(kv, "Value");   // Dictionary<string,Part> -- unwrap KeyValuePair
                        if (part == null) continue;
                        total++;

                        string pname = "?";
                        try { pname = (string)Get(Get(part, "orientation"), "name"); } catch { }

                        float mass = ToF(GetWrapped2(Get(part, "mass")));
                        object com = Get(part, "centerOfMass");
                        float comX = ToF(GetWrapped2(Get(com, "x")));
                        float comY = ToF(GetWrapped2(Get(com, "y")));

                        var vsb = new StringBuilder();
                        vsb.Append("{\"name\":").Append(Q(pname));
                        vsb.Append(",\"mass\":").Append(Num(mass));
                        vsb.Append(",\"centerOfMassX\":").Append(Num(comX));
                        vsb.Append(",\"centerOfMassY\":").Append(Num(comY));
                        vsb.Append(",\"variables\":").Append(DumpVariablesModule(part));
                        vsb.Append(",\"magnetPoints\":").Append(DumpMagnetPoints(part));
                        vsb.Append("}");
                        items.Add(vsb.ToString());
                    }

                    object variantsObj = Get(FindComponent("SFS.Parts.PartsLoader"), "partVariants");
                    var venum = variantsObj as System.Collections.IEnumerable;
                    var variantItems = new List<string>();
                    int variantTotal = 0;
                    if (venum != null)
                    {
                        foreach (object kv in venum)
                        {
                            object variant = Get(kv, "Value");
                            if (variant == null) continue;
                            variantTotal++;
                            string vkey = "?";
                            try { vkey = (string)Get(kv, "Key"); } catch { }
                            variantItems.Add("{\"key\":" + Q(vkey) + ",\"data\":" + DumpObjectFieldsGeneric(variant) + "}");
                        }
                    }

                    var outSb = new StringBuilder();
                    outSb.Append("{\"parts\":[").Append(string.Join(",", items.ToArray())).Append("],\"partsTotal\":").Append(total);
                    outSb.Append(",\"variants\":[").Append(string.Join(",", variantItems.ToArray())).Append("],\"variantsTotal\":").Append(variantTotal);
                    outSb.Append("}");
                    Write("sfs_probe_parts_index.json", outSb, "getparts parts=" + total + " variants=" + variantTotal);
                    ProbeMod.Result("getparts: " + total + " parts, " + variantTotal + " variants -> sfs_probe_parts_index.json");
                    break;
                }

                case "aeroformula":
                {
                    // Reads the 4 serialized AeroFormula coefficients (velPow,
                    // densityPow, tempOffset, m) that GetTemperature() needs --
                    // confirmed via IL to be serialized Unity data, not IL
                    // literals, so they cannot be known without a live read.
                    // Path per docs/sfs_reference/02-drag-aero/AeroFormula.md:
                    // GameManager.main.aeroData.Formula -- tries that property
                    // first, falls back to aeroData.formulaHolder.formula if the
                    // property isn't there, and reports which path actually
                    // worked rather than assuming.
                    object gmAF = FindComponent("SFS.World.GameManager");
                    object aeroData = Get(gmAF, "aeroData");
                    if (aeroData == null) { ProbeMod.Result("aeroformula: FAILED reason=no_aeroData"); break; }

                    object formula = Get(aeroData, "Formula");
                    string formulaPath = "aeroData.Formula";
                    if (formula == null)
                    {
                        object holderAF = Get(aeroData, "formulaHolder");
                        formula = Get(holderAF, "formula");
                        formulaPath = "aeroData.formulaHolder.formula";
                    }
                    if (formula == null)
                    {
                        ProbeMod.Result("aeroformula: FAILED reason=formula_not_found (tried aeroData.Formula and aeroData.formulaHolder.formula)");
                        break;
                    }

                    float velPow = ToF(Get(formula, "velPow"));
                    float densityPow = ToF(Get(formula, "densityPow"));
                    float tempOffset = ToF(Get(formula, "tempOffset"));
                    float mCoef = ToF(Get(formula, "m"));

                    var afsb = new StringBuilder();
                    afsb.Append("{\"path\":").Append(Q(formulaPath));
                    afsb.Append(",\"velPow\":").Append(Num(velPow));
                    afsb.Append(",\"densityPow\":").Append(Num(densityPow));
                    afsb.Append(",\"tempOffset\":").Append(Num(tempOffset));
                    afsb.Append(",\"m\":").Append(Num(mCoef));
                    afsb.Append("}");
                    Write("sfs_probe_aeroformula.json", afsb, "aeroformula coefficients via " + formulaPath);
                    ProbeMod.Result("aeroformula: velPow=" + velPow + " densityPow=" + densityPow +
                                     " tempOffset=" + tempOffset + " m=" + mCoef +
                                     " (via " + formulaPath + ") -> sfs_probe_aeroformula.json");
                    break;
                }

                case "atmophysics":
                {
                    // Reads planet.data.atmospherePhysics for the current
                    // rocket's planet -- specifically minHeatingVelocityMultiplier
                    // and shockwaveIntensity, the two float32 fields
                    // AeroModule.GetTemperatureAndShockwave actually consumes.
                    // Needed to complete the reentry-temperature formula: the
                    // 3.0.ctor() default (1.0f) is NOT necessarily what Earth's
                    // real planet file specifies -- per the project's data-trust
                    // rule, this must be read live, not assumed. Also dumps
                    // height/density/curve for reference (already scaled by
                    // Difficulty.ScalePlanetData at this point, per
                    // Atmosphere_Physics.md).
                    object rAP = ActiveRocket();
                    if (rAP == null) { ProbeMod.Result("atmophysics: no active rocket"); break; }
                    object locAP = Unwrap(Get(rAP, "location"));
                    object planetAP = Unwrap(Get(locAP, "planet"));
                    if (planetAP == null) { ProbeMod.Result("atmophysics: no planet"); break; }
                    object dataAP = Get(planetAP, "data");
                    object atmoAP = Get(dataAP, "atmospherePhysics");
                    if (atmoAP == null) { ProbeMod.Result("atmophysics: FAILED reason=no_atmospherePhysics"); break; }

                    double heightAP = ToD(Get(atmoAP, "height"));
                    double densityAP = ToD(Get(atmoAP, "density"));
                    double curveAP = ToD(Get(atmoAP, "curve"));
                    float minHeatVelMult = ToF(Get(atmoAP, "minHeatingVelocityMultiplier"));
                    float shockwaveIntensity = ToF(Get(atmoAP, "shockwaveIntensity"));
                    string bodyNameAP = Get(planetAP, "codeName") as string;

                    var apsb = new StringBuilder();
                    apsb.Append("{\"body\":").Append(Q(bodyNameAP));
                    apsb.Append(",\"height\":").Append(Num(heightAP));
                    apsb.Append(",\"density\":").Append(Num(densityAP));
                    apsb.Append(",\"curve\":").Append(Num(curveAP));
                    apsb.Append(",\"minHeatingVelocityMultiplier\":").Append(Num(minHeatVelMult));
                    apsb.Append(",\"shockwaveIntensity\":").Append(Num(shockwaveIntensity));
                    apsb.Append("}");
                    Write("sfs_probe_atmophysics.json", apsb, "atmophysics for " + bodyNameAP);
                    ProbeMod.Result("atmophysics: body=" + bodyNameAP + " minHeatingVelocityMultiplier=" +
                                     minHeatVelMult + " shockwaveIntensity=" + shockwaveIntensity +
                                     " -> sfs_probe_atmophysics.json");
                    break;
                }

                case "terrain":
                {
                    // First live terrain check for this project. Reads REAL
                    // per-angle terrain height via Planet.GetTerrainHeightAtAngles
                    // (confirmed via IL: maxTerrainHeight is only a fast-reject
                    // bound, not real geometry -- see sfs_source_reference.md D4.4).
                    // Sweeps a fan of angles around the active craft's current
                    // angular position so we can directly see real variation
                    // across the sweep, rather than trusting maxTerrainHeight as
                    // if it were the surface. Also cross-checks Location.GetTerrainHeight
                    // (the ground-clearance figure) against Height minus the swept
                    // value at offset 0 -- those two should agree if both paths are
                    // reading the same underlying function.
                    // arg (optional): comma-separated list of degree offsets, e.g.
                    // "terrain -30,-10,-2,0,2,10,30". Defaults to a standard fan if
                    // no arg given.
                    object rTer = ActiveRocket();
                    if (rTer == null) { ProbeMod.Result("terrain: no active rocket"); break; }
                    object locTer = Unwrap(Get(rTer, "location"));
                    object planetTer = Unwrap(Get(locTer, "planet"));
                    if (planetTer == null) { ProbeMod.Result("terrain: no planet"); break; }

                    object posTer = Get(locTer, "position");
                    double posX = ToD(Get(posTer, "x"));
                    double posY = ToD(Get(posTer, "y"));
                    double curAngleRad = Math.Atan2(posY, posX);
                    double curHeight = ToD(Get(locTer, "Height"));
                    double maxTerHeight = ToD(Get(planetTer, "maxTerrainHeight"));
                    double planetRadiusTer = ToD(Get(planetTer, "Radius"));
                    string bodyNameTer = Get(planetTer, "codeName") as string;

                    double[] offsetsDeg;
                    if (!string.IsNullOrEmpty(arg))
                    {
                        string[] parts = arg.Split(',');
                        offsetsDeg = new double[parts.Length];
                        for (int i = 0; i < parts.Length; i++)
                            offsetsDeg[i] = double.Parse(parts[i], CultureInfo.InvariantCulture);
                    }
                    else
                    {
                        offsetsDeg = new double[] { -30, -20, -10, -5, -2, -1, 0, 1, 2, 5, 10, 20, 30 };
                    }

                    double[] anglesRad = new double[offsetsDeg.Length];
                    for (int i = 0; i < offsetsDeg.Length; i++)
                        anglesRad[i] = curAngleRad + offsetsDeg[i] * Math.PI / 180.0;

                    object heightsObjWater = InvokeReturn(planetTer, "GetTerrainHeightAtAngles",
                        new object[] { anglesRad, true });
                    object heightsObjNoWater = InvokeReturn(planetTer, "GetTerrainHeightAtAngles",
                        new object[] { anglesRad, false });
                    double[] heightsWater = heightsObjWater as double[];
                    double[] heightsNoWater = heightsObjNoWater as double[];
                    if (heightsWater == null)
                    {
                        ProbeMod.Result("terrain: FAILED reason=GetTerrainHeightAtAngles_returned_null");
                        break;
                    }

                    // Cross-check: Location.GetTerrainHeight(clampToWater) should
                    // equal Height - GetTerrainHeightAtAngle(currentAngle, clampToWater).
                    object groundClearObj = InvokeReturn(locTer, "GetTerrainHeight", new object[] { true });
                    double groundClearance = groundClearObj != null ? ToD(groundClearObj) : double.NaN;

                    var terSb = new StringBuilder();
                    terSb.Append("{\"body\":").Append(Q(bodyNameTer));
                    terSb.Append(",\"maxTerrainHeight\":").Append(Num(maxTerHeight));
                    terSb.Append(",\"planetRadius\":").Append(Num(planetRadiusTer));
                    terSb.Append(",\"currentAngleDeg\":").Append(Num(curAngleRad * 180.0 / Math.PI));
                    terSb.Append(",\"currentHeight\":").Append(Num(curHeight));
                    terSb.Append(",\"groundClearance_clampWater\":").Append(Num(groundClearance));
                    terSb.Append(",\"sweep\":[");
                    for (int i = 0; i < offsetsDeg.Length; i++)
                    {
                        if (i > 0) terSb.Append(",");
                        double hw = heightsWater[i];
                        double hn = heightsNoWater != null ? heightsNoWater[i] : double.NaN;
                        terSb.Append("{\"offsetDeg\":").Append(Num(offsetsDeg[i]));
                        terSb.Append(",\"terrainHeight_clampWater\":").Append(Num(hw));
                        terSb.Append(",\"terrainHeight_noClamp\":").Append(Num(hn));
                        terSb.Append("}");
                    }
                    terSb.Append("]}");
                    Write("sfs_probe_terrain.json", terSb, "terrain sweep for " + bodyNameTer);
                    ProbeMod.Result("terrain: body=" + bodyNameTer + " maxTerrainHeight=" + maxTerHeight +
                                     " currentHeight=" + curHeight + " groundClearance=" + groundClearance +
                                     " sweep0=" + heightsWater[offsetsDeg.Length / 2] +
                                     " -> sfs_probe_terrain.json");
                    break;
                }

                case "terraingeo":
                {
                    // Remaining terrain surface queries after height:
                    // GetTerrainNormal, GetTerrainColor, IsInsideTerrain,
                    // GetMaxLOD. All [CONFIRMED] in IL (signatures only,
                    // @148158-@149756) but never called live before now.
                    // IsInsideTerrain is exercised at three points: the
                    // real craft position, a synthetic point 5m below the
                    // local surface (same angle), and a synthetic point
                    // 1000m above the maxTerrainHeight fast-reject bound
                    // (same angle) -- since we can't teleport the real
                    // craft mid-session, these synthetic Double2 points are
                    // built via reflection on the same Double2 type as the
                    // craft's live position, to directly exercise both the
                    // fast-reject branch and the real surface-comparison
                    // branch inside IsInsideTerrain.
                    object rTg = ActiveRocket();
                    if (rTg == null) { ProbeMod.Result("terraingeo: no active rocket"); break; }
                    object locTg = Unwrap(Get(rTg, "location"));
                    object planetTg = Unwrap(Get(locTg, "planet"));
                    if (planetTg == null) { ProbeMod.Result("terraingeo: no planet"); break; }

                    object posTg = Get(locTg, "position");
                    Type double2Type = posTg.GetType();
                    FieldInfo xField = double2Type.GetField("x");
                    FieldInfo yField = double2Type.GetField("y");
                    double posXg = ToD(Get(posTg, "x"));
                    double posYg = ToD(Get(posTg, "y"));
                    double angleTg = Math.Atan2(posYg, posXg);
                    double radiusHere = Math.Sqrt(posXg * posXg + posYg * posYg);

                    double maxTerHeightTg = ToD(Get(planetTg, "maxTerrainHeight"));
                    double planetRadiusTg = ToD(Get(planetTg, "Radius"));
                    string bodyNameTg = Get(planetTg, "codeName") as string;

                    object terrainHereObj = InvokeReturn(planetTg, "GetTerrainHeightAtAngle",
                        new object[] { angleTg, true });
                    double terrainHereWater = terrainHereObj != null ? ToD(terrainHereObj) : double.NaN;

                    object underPos = Activator.CreateInstance(double2Type);
                    double underRadius = planetRadiusTg + terrainHereWater - 5.0;
                    xField.SetValue(underPos, underRadius * Math.Cos(angleTg));
                    yField.SetValue(underPos, underRadius * Math.Sin(angleTg));

                    object spacePos = Activator.CreateInstance(double2Type);
                    double spaceRadius = planetRadiusTg + maxTerHeightTg + 1000.0;
                    xField.SetValue(spacePos, spaceRadius * Math.Cos(angleTg));
                    yField.SetValue(spacePos, spaceRadius * Math.Sin(angleTg));

                    object insideReal = InvokeReturn(planetTg, "IsInsideTerrain", new object[] { posTg, 0.0, true });
                    object insideUnder = InvokeReturn(planetTg, "IsInsideTerrain", new object[] { underPos, 0.0, true });
                    object insideSpace = InvokeReturn(planetTg, "IsInsideTerrain", new object[] { spacePos, 0.0, true });

                    object normalObj = InvokeReturn(planetTg, "GetTerrainNormal", new object[] { posTg });
                    double normalX = double.NaN, normalY = double.NaN;
                    if (normalObj != null)
                    {
                        normalX = ToD(Get(normalObj, "x"));
                        normalY = ToD(Get(normalObj, "y"));
                    }

                    object colorObj = InvokeReturn(planetTg, "GetTerrainColor", new object[] { posTg });
                    string colorStr = "null";
                    if (colorObj != null)
                    {
                        float cr = ToF(Get(colorObj, "r"));
                        float cg = ToF(Get(colorObj, "g"));
                        float cb = ToF(Get(colorObj, "b"));
                        float ca = ToF(Get(colorObj, "a"));
                        colorStr = "{\"r\":" + Num(cr) + ",\"g\":" + Num(cg) + ",\"b\":" + Num(cb) +
                                   ",\"a\":" + Num(ca) + "}";
                    }

                    object maxLodObj = InvokeReturn(planetTg, "GetMaxLOD", new object[0]);

                    var tgSb = new StringBuilder();
                    tgSb.Append("{\"body\":").Append(Q(bodyNameTg));
                    tgSb.Append(",\"currentAngleDeg\":").Append(Num(angleTg * 180.0 / Math.PI));
                    tgSb.Append(",\"currentRadius\":").Append(Num(radiusHere));
                    tgSb.Append(",\"terrainHeightHere_clampWater\":").Append(Num(terrainHereWater));
                    tgSb.Append(",\"isInsideTerrain_realPosition\":").Append(ToB(insideReal) ? "true" : "false");
                    tgSb.Append(",\"isInsideTerrain_5mUnderground\":").Append(ToB(insideUnder) ? "true" : "false");
                    tgSb.Append(",\"isInsideTerrain_1000mAboveBound\":").Append(ToB(insideSpace) ? "true" : "false");
                    tgSb.Append(",\"terrainNormal\":{\"x\":").Append(Num(normalX)).Append(",\"y\":").Append(Num(normalY)).Append("}");
                    tgSb.Append(",\"terrainColor\":").Append(colorStr);
                    tgSb.Append(",\"maxLOD\":").Append(maxLodObj != null ? maxLodObj.ToString() : "null");
                    tgSb.Append("}");
                    Write("sfs_probe_terraingeo.json", tgSb, "terrain normal/color/IsInsideTerrain/MaxLOD for " + bodyNameTg);
                    ProbeMod.Result("terraingeo: body=" + bodyNameTg +
                                     " insideReal=" + ToB(insideReal) + " insideUnder=" + ToB(insideUnder) +
                                     " insideSpace=" + ToB(insideSpace) +
                                     " normal=(" + normalX + "," + normalY + ")" +
                                     " -> sfs_probe_terraingeo.json");
                    break;
                }

                case "difficulty":
                {
                    // Item 4/6 from the heat gap list: reads the ACTUAL difficulty
                    // heat multipliers instead of assuming Normal=1.0/1.0 (which broke
                    // this project's own data-trust rule -- every other formula reads
                    // live, this one didn't yet). Also checks aeroData.testShock/
                    // testReentry, the debug override that would silently produce fake
                    // temperatures unrelated to real flight state if either were true.
                    object worldBase = Get(FindType("SFS.Base"), "worldBase");
                    if (worldBase == null) { ProbeMod.Result("difficulty: FAILED reason=no_world_loaded"); break; }
                    object settings = Get(worldBase, "settings");
                    object difficulty = Get(settings, "difficulty");
                    if (difficulty == null) { ProbeMod.Result("difficulty: FAILED reason=no_difficulty"); break; }

                    string diffName = "?";
                    try { diffName = Get(difficulty, "difficulty").ToString(); } catch { }
                    float heatVelMult = ToF(Get(difficulty, "HeatVelocityMultiplier"));
                    float minHeatVelMult = ToF(Get(difficulty, "MinHeatVelocityMultiplier"));
                    double ispMult = ToD(Get(difficulty, "IspMultiplier"));
                    double dryMassMult = ToD(Get(difficulty, "DryMassMultiplier"));

                    object gmD = FindComponent("SFS.World.GameManager");
                    object aeroDataD = Get(gmD, "aeroData");
                    bool testShock = false, testReentry = false;
                    try { testShock = ToB(Get(aeroDataD, "testShock")); } catch { }
                    try { testReentry = ToB(Get(aeroDataD, "testReentry")); } catch { }

                    var dsb = new StringBuilder();
                    dsb.Append("{\"difficulty\":").Append(Q(diffName));
                    dsb.Append(",\"heatVelocityMultiplier\":").Append(Num(heatVelMult));
                    dsb.Append(",\"minHeatVelocityMultiplier\":").Append(Num(minHeatVelMult));
                    dsb.Append(",\"ispMultiplier\":").Append(Num(ispMult));
                    dsb.Append(",\"dryMassMultiplier\":").Append(Num(dryMassMult));
                    dsb.Append(",\"aeroTestShock\":").Append(testShock ? "true" : "false");
                    dsb.Append(",\"aeroTestReentry\":").Append(testReentry ? "true" : "false");
                    dsb.Append("}");
                    Write("sfs_probe_difficulty.json", dsb, "difficulty settings");
                    ProbeMod.Result("difficulty: " + diffName + " heatVelMult=" + heatVelMult +
                                     " minHeatVelMult=" + minHeatVelMult + " testShock=" + testShock +
                                     " testReentry=" + testReentry + " -> sfs_probe_difficulty.json");
                    break;
                }

                case "jointgraph":
                {
                    // Item 3 from the heat gap list: dumps the REAL live joint
                    // connectivity graph (Rocket.jointsGroup.joints), confirmed via IL
                    // to be a genuine index (unlike Part.modules' lazy memo -- see
                    // docs/sfs_reference/11-joints-docking/joints-and-docking.md).
                    // Each PartJoint is an undirected edge (a, b, anchor) -- no
                    // strength or type, since SFS joints are graph edges, not physics
                    // joint components. Combined with heatParts (in truth.jsonl), this
                    // lets a caller predict WHICH joint breaks next and how many parts
                    // it takes with it, not just that partCount will drop.
                    object rJG = ActiveRocket();
                    if (rJG == null) { ProbeMod.Result("jointgraph: no active rocket"); break; }
                    object jointsGroup = Get(rJG, "jointsGroup");
                    if (jointsGroup == null) { ProbeMod.Result("jointgraph: FAILED reason=no_jointsGroup"); break; }
                    object joints = Get(jointsGroup, "joints");
                    var jEn = joints as System.Collections.IEnumerable;
                    var jointItems = new List<string>();
                    int jointCount = 0;
                    if (jEn != null)
                    {
                        foreach (object j in jEn)
                        {
                            jointCount++;
                            object pa = Get(j, "a");
                            object pb = Get(j, "b");
                            string nameA = "?", nameB = "?";
                            try { nameA = (string)Get(Get(pa, "displayName"), "TranslatableName"); } catch { }
                            try { nameB = (string)Get(Get(pb, "displayName"), "TranslatableName"); } catch { }
                            object anchor = Get(j, "anchor");
                            float ax = ToF(Get(anchor, "x"));
                            float ay = ToF(Get(anchor, "y"));
                            jointItems.Add("{\"a\":" + Q(nameA) + ",\"b\":" + Q(nameB) +
                                           ",\"anchorX\":" + Num(ax) + ",\"anchorY\":" + Num(ay) + "}");
                        }
                    }
                    object partsListJG = Get(jointsGroup, "parts");
                    var pEnJG = partsListJG as System.Collections.ICollection;
                    int partCountJG = pEnJG != null ? pEnJG.Count : -1;

                    var jsb = new StringBuilder();
                    jsb.Append("{\"joints\":[").Append(string.Join(",", jointItems.ToArray())).Append("]");
                    jsb.Append(",\"jointCount\":").Append(jointCount);
                    jsb.Append(",\"partCount\":").Append(partCountJG);
                    jsb.Append("}");
                    Write("sfs_probe_jointgraph.json", jsb, "jointgraph joints=" + jointCount + " parts=" + partCountJG);
                    ProbeMod.Result("jointgraph: " + jointCount + " joints, " + partCountJG +
                                     " parts -> sfs_probe_jointgraph.json");
                    break;
                }

                case "turn":
                {
                    // Sets arrowkeys.turnAxis directly -- the SAME state
                    // Rocket.ApplyTorque reads to drive real rotation
                    // (turnAxis * torque_effective * dt / mass, torque_effective
                    // = sum of enabled TorqueModule.torque). IMPORTANT: this
                    // rocket's part list (Capsule/Parachute/Fuel Tank/Nose Cone/
                    // Hawk Engine) contains no RCS thruster and no reaction
                    // wheel, so it almost certainly has NO TorqueModule at all --
                    // if so, torque_effective is 0 and this write has ZERO
                    // physical effect via the torque path on THIS rocket. The
                    // only remaining path is gimbal (RecalculateGimbal), which
                    // only deflects while an engine's throttle_Out > 0. No
                    // clamp is applied here, matching the game's own confirmed
                    // behavior on this branch (nothing clamps turnAxis to +-1 on
                    // a direct write) -- pass values responsibly.
                    float turnV = float.Parse(arg, CultureInfo.InvariantCulture);
                    object rTurn = ActiveRocket();
                    object arrowkeys = Get(rTurn, "arrowkeys");
                    bool turnOk = SetWrapped(arrowkeys, "turnAxis", turnV);
                    ProbeMod.Result("turn " + turnV + (turnOk ? " ok" : " FAILED (arrowkeys obj=" + Name(arrowkeys) + ")"));
                    break;
                }

                case "setrot":
                {
                    // INSTANT snap, not a simulated turn -- writes rb2d.rotation
                    // directly (Unity's own plain Rigidbody2D property, degrees,
                    // NOT one of SFS's Composed/Reference wrapper types) and
                    // zeroes rb2d.angularVelocity so each checkpoint starts clean
                    // rather than carrying over spin from whatever happened
                    // before. Teleports orientation in one frame; does not
                    // simulate the rotation getting there -- treat data
                    // immediately after this command with less confidence about
                    // "how did it get here", full confidence about "what does it
                    // do FROM here".
                    float deg = float.Parse(arg, CultureInfo.InvariantCulture);
                    object rSetrot = ActiveRocket();
                    object rbSetrot = Get(rSetrot, "rb2d");
                    if (rbSetrot == null) { ProbeMod.Result("setrot: FAILED reason=no_rb2d"); break; }
                    bool setrotOk = true;
                    try
                    {
                        PropertyInfo rotProp = rbSetrot.GetType().GetProperty("rotation", BindingFlags.Public | BindingFlags.Instance);
                        PropertyInfo angvProp = rbSetrot.GetType().GetProperty("angularVelocity", BindingFlags.Public | BindingFlags.Instance);
                        if (rotProp != null) rotProp.SetValue(rbSetrot, deg, null); else setrotOk = false;
                        if (angvProp != null) angvProp.SetValue(rbSetrot, 0f, null); else setrotOk = false;
                    }
                    catch (Exception e)
                    {
                        ProbeMod.Result("setrot: FAILED reason=exception " + e.Message);
                        break;
                    }
                    ProbeMod.Result("setrot " + deg + "deg" + (setrotOk ? " ok (angularVelocity zeroed)" : " PARTIAL (property not found)"));
                    break;
                }

                case "script":
                {
                    // Arms a whole conditional flight plan in one call -- see the
                    // "scripted flight plans" region below Command() for the full
                    // syntax and design rationale. Path can't contain a space-2
                    // split ambiguity here since ';'/'&&' are the real delimiters,
                    // but the WHOLE rest of the line is the spec (commands inside
                    // steps have their own spaces), so split into exactly 2 pieces
                    // like loadblueprint/loadblueprintbuild do.
                    string[] partsScript = line.Split(new char[] { ' ' }, 2);
                    string specScript = partsScript.Length > 1 ? partsScript[1].Trim() : null;
                    if (string.IsNullOrEmpty(specScript))
                    {
                        ProbeMod.Result("script: FAILED reason=no_spec");
                        break;
                    }
                    try
                    {
                        int n = LoadScript(specScript);
                        ProbeMod.Result("script: armed " + n + " step(s)");
                    }
                    catch (Exception e)
                    {
                        ProbeMod.Result("script: FAILED reason=parse_error " + e.Message);
                    }
                    break;
                }

                case "scriptstatus":
                {
                    int pending = 0, done = 0;
                    foreach (ScriptStep s in ScriptQueue) { if (s.Done) done++; else pending++; }
                    var stsb = new StringBuilder();
                    stsb.Append("{\"pending\":").Append(pending).Append(",\"done\":").Append(done);
                    stsb.Append(",\"steps\":[");
                    for (int i = 0; i < ScriptQueue.Count; i++)
                    {
                        ScriptStep s = ScriptQueue[i];
                        if (i > 0) stsb.Append(",");
                        stsb.Append("{\"field\":").Append(Q(s.Field)).Append(",\"op\":").Append(Q(s.Op));
                        stsb.Append(",\"value\":").Append(Num(s.Value)).Append(",\"commands\":[");
                        for (int j = 0; j < s.Commands.Length; j++)
                        {
                            if (j > 0) stsb.Append(",");
                            stsb.Append(Q(s.Commands[j]));
                        }
                        stsb.Append("],\"done\":").Append(s.Done ? "true" : "false").Append("}");
                    }
                    stsb.Append("]}");
                    ProbeMod.Result("scriptstatus: pending=" + pending + " done=" + done + " " + stsb.ToString());
                    break;
                }

                case "scriptclear":
                {
                    int cleared = ScriptQueue.Count;
                    ScriptQueue.Clear();
                    ProbeMod.Result("scriptclear: cleared " + cleared + " step(s)");
                    break;
                }

                case "rcsinfo":
                {
                    // Live read of the two per-part-serialized RcsModule
                    // thresholds (directionAngleThreshold, torqueAngleThreshold)
                    // confirmed via IL re-read 2026-08-30 -- can only be read
                    // live, never from IL literals. Also dumps thrust, ISP, and
                    // thrustPosition (local) per module, and per-thruster
                    // thrustNormal (local), everything needed to reconstruct
                    // TorqueThrust/DirectionThrust's selection logic and the
                    // resulting force for a live validation.
                    object rRcs = ActiveRocket();
                    if (rRcs == null) { ProbeMod.Result("rcsinfo: no active rocket"); break; }
                    object holderRcs = Get(rRcs, "partHolder");
                    object partsRcs = Get(holderRcs, "parts");
                    var partsEnRcs = partsRcs as System.Collections.IEnumerable;
                    var modules = new List<string>();
                    if (partsEnRcs != null)
                    {
                        foreach (object part in partsEnRcs)
                        {
                            foreach (object mv in ModuleValues(part))
                            {
                                if (mv.GetType().Name != "RcsModule") continue;
                                float dAngle = ToF(Get(mv, "directionAngleThreshold"));
                                float tAngle = ToF(Get(mv, "torqueAngleThreshold"));
                                float thrustVal = ToF(Get(mv, "thrust"));
                                float ispVal = ToF(Get(mv, "ISP"));
                                object thrustPos = Get(mv, "thrustPosition");
                                float posX = ToF(Get(thrustPos, "x"));
                                float posY = ToF(Get(thrustPos, "y"));

                                var thrusterList = new List<string>();
                                object thrusters = Get(mv, "thrusters");
                                var thEn = thrusters as System.Collections.IEnumerable;
                                if (thEn != null)
                                {
                                    foreach (object th in thEn)
                                    {
                                        object normal = Get(th, "thrustNormal");
                                        float nx = ToF(Get(normal, "x"));
                                        float ny = ToF(Get(normal, "y"));
                                        thrusterList.Add("{\"normalX\":" + Num(nx) + ",\"normalY\":" + Num(ny) + "}");
                                    }
                                }

                                var msb = new StringBuilder();
                                msb.Append("{\"directionAngleThreshold\":").Append(Num(dAngle));
                                msb.Append(",\"torqueAngleThreshold\":").Append(Num(tAngle));
                                msb.Append(",\"thrust\":").Append(Num(thrustVal));
                                msb.Append(",\"ISP\":").Append(Num(ispVal));
                                msb.Append(",\"thrustPositionX\":").Append(Num(posX));
                                msb.Append(",\"thrustPositionY\":").Append(Num(posY));
                                msb.Append(",\"thrusterCount\":").Append(thrusterList.Count);
                                msb.Append(",\"thrusters\":[").Append(string.Join(",", thrusterList.ToArray())).Append("]");
                                msb.Append("}");
                                modules.Add(msb.ToString());
                            }
                        }
                    }
                    var rsb = new StringBuilder();
                    rsb.Append("{\"moduleCount\":").Append(modules.Count);
                    rsb.Append(",\"modules\":[").Append(string.Join(",", modules.ToArray())).Append("]}");
                    Write("sfs_probe_rcsinfo.json", rsb, "rcsinfo modules=" + modules.Count);
                    ProbeMod.Result("rcsinfo: " + modules.Count + " RcsModule(s) found -> sfs_probe_rcsinfo.json" +
                                     (modules.Count == 0 ? " (this rocket has no RCS parts)" : ""));
                    break;
                }

                case "rcsforce":
                {
                    // Live validation support for RCS force magnitude/direction
                    // and the N^2 firing-count arithmetic (sfs_source_reference.md
                    // D3.1). Replicates RcsModule.FixedUpdate's exact real-call
                    // sequence per module -- NOT a reimplementation of the game's
                    // math, but the same calls the game itself makes, via
                    // reflection: Rigidbody2D.worldCenterOfMass,
                    // Transform.TransformPoint, Transform_Utility.TransformVectorUnscaled,
                    // and the private TorqueThrust/DirectionThrust selection
                    // methods are all invoked directly on the live objects. Only
                    // the final vector sum / scaling (sumNormal, count, the
                    // thrust*count*9.8 force formula) is arithmetic done here,
                    // matching FixedUpdate's own IL exactly (confirmed via a
                    // fresh IL read 2026-08-30, RVA 0x65f34).
                    object rF = ActiveRocket();
                    if (rF == null) { ProbeMod.Result("rcsforce: no active rocket"); break; }
                    object rb2dF = Get(rF, "rb2d");
                    if (rb2dF == null) { ProbeMod.Result("rcsforce: no rb2d"); break; }
                    object worldCoMObj = Get(rb2dF, "worldCenterOfMass");
                    if (worldCoMObj == null) { ProbeMod.Result("rcsforce: worldCenterOfMass read failed"); break; }
                    float comX = ToF(Get(worldCoMObj, "x"));
                    float comY = ToF(Get(worldCoMObj, "y"));
                    double rocketMass = ToD(Get(rb2dF, "mass"));

                    object holderF = Get(rF, "partHolder");
                    object partsF = Get(holderF, "parts");
                    var partsEnF = partsF as System.Collections.IEnumerable;
                    var moduleResults = new List<string>();
                    float totalForceX = 0f, totalForceY = 0f;
                    double totalMassFlow = 0.0;
                    Type vector3TypeCache = null;
                    MethodInfo transformPointMethod = null;
                    MethodInfo vec2ToVec3Method = null;

                    if (partsEnF != null)
                    {
                        foreach (object part in partsEnF)
                        {
                            foreach (object mv in ModuleValues(part))
                            {
                                if (mv.GetType().Name != "RcsModule") continue;

                                bool rcsOnF = ToB(Get(mv, "RCS_On"));
                                float turnAxisF = ToF(Get(mv, "TurnAxis"));
                                object dirAxisObj = Get(mv, "DirectionalAxis");
                                float dirAxisX = ToF(Get(dirAxisObj, "x"));
                                float dirAxisY = ToF(Get(dirAxisObj, "y"));
                                double dirAxisSqrMag = (double)dirAxisX * dirAxisX + (double)dirAxisY * dirAxisY;

                                // Matches FixedUpdate's own top-level early-out exactly:
                                // Rocket==null / !RCS_On / (both axes under threshold) -> no force, zero mass flow.
                                bool moduleDeadzoned = !rcsOnF ||
                                    (Math.Abs(turnAxisF) < 0.01f && dirAxisSqrMag < 0.01);

                                object rcsTransform = Get(mv, "transform");
                                float thrustVal = ToF(Get(mv, "thrust"));
                                float ispVal = ToF(Get(mv, "ISP"));
                                object thrustPosLocal = Get(mv, "thrustPosition");

                                if (vector3TypeCache == null && rcsTransform != null && thrustPosLocal != null)
                                {
                                    // Resolve UnityEngine overloaded methods explicitly by
                                    // parameter type -- these live in UnityEngine.CoreModule,
                                    // outside this project's own IL dump, and Unity commonly
                                    // has multiple overloads (TransformPoint(Vector3) vs.
                                    // TransformPoint(float,float,float); Vector2's several
                                    // op_Implicit conversions) that would throw
                                    // AmbiguousMatchException on a plain GetMethod(name) call.
                                    Type vector2TypeLocal = thrustPosLocal.GetType();
                                    vec2ToVec3Method = vector2TypeLocal.GetMethod("op_Implicit",
                                        BindingFlags.Public | BindingFlags.Static, null,
                                        new Type[] { vector2TypeLocal }, null);
                                    if (vec2ToVec3Method != null)
                                    {
                                        vector3TypeCache = vec2ToVec3Method.ReturnType;
                                        transformPointMethod = rcsTransform.GetType().GetMethod("TransformPoint",
                                            BindingFlags.Public | BindingFlags.Instance, null,
                                            new Type[] { vector3TypeCache }, null);
                                    }
                                }

                                float thrustPosWorldX = float.NaN, thrustPosWorldY = float.NaN;
                                if (vec2ToVec3Method != null && transformPointMethod != null && rcsTransform != null)
                                {
                                    object thrustPosVec3 = vec2ToVec3Method.Invoke(null, new object[] { thrustPosLocal });
                                    object worldPosVec3 = transformPointMethod.Invoke(rcsTransform, new object[] { thrustPosVec3 });
                                    thrustPosWorldX = ToF(Get(worldPosVec3, "x"));
                                    thrustPosWorldY = ToF(Get(worldPosVec3, "y"));
                                }

                                float posToComX = thrustPosWorldX == thrustPosWorldX ? comX - thrustPosWorldX : float.NaN;
                                float posToComY = thrustPosWorldY == thrustPosWorldY ? comY - thrustPosWorldY : float.NaN;
                                object posToComVec2 = null;
                                if (posToComX == posToComX && thrustPosLocal != null)
                                {
                                    posToComVec2 = Activator.CreateInstance(thrustPosLocal.GetType());
                                    thrustPosLocal.GetType().GetField("x").SetValue(posToComVec2, posToComX);
                                    thrustPosLocal.GetType().GetField("y").SetValue(posToComVec2, posToComY);
                                }

                                object transformUtilType = FindType("Transform_Utility");
                                float sumNormalX = 0f, sumNormalY = 0f;
                                float firingCount = 0f;
                                int thrusterTotal = 0;
                                var thrusterResults = new List<string>();

                                object thrustersF = Get(mv, "thrusters");
                                var thEnF = thrustersF as System.Collections.IEnumerable;
                                if (thEnF != null && !moduleDeadzoned && transformUtilType != null && rcsTransform != null && posToComVec2 != null)
                                {
                                    foreach (object th in thEnF)
                                    {
                                        thrusterTotal++;
                                        object localNormal = Get(th, "thrustNormal");
                                        object worldNormalObj = InvokeReturn(transformUtilType, "TransformVectorUnscaled",
                                            new object[] { rcsTransform, localNormal });
                                        if (worldNormalObj == null) continue;
                                        float wnx = ToF(Get(worldNormalObj, "x"));
                                        float wny = ToF(Get(worldNormalObj, "y"));

                                        object fireTorqueObj = InvokeReturn(mv, "TorqueThrust",
                                            new object[] { worldNormalObj, posToComVec2 });
                                        object fireDirObj = InvokeReturn(mv, "DirectionThrust",
                                            new object[] { worldNormalObj });
                                        bool fires = ToB(fireTorqueObj) || ToB(fireDirObj);

                                        thrusterResults.Add("{\"worldNormalX\":" + Num(wnx) + ",\"worldNormalY\":" + Num(wny) +
                                            ",\"firing\":" + (fires ? "true" : "false") + "}");

                                        if (fires) { sumNormalX += wnx; sumNormalY += wny; firingCount += 1f; }
                                    }
                                }
                                else if (thEnF != null)
                                {
                                    foreach (object th in thEnF) thrusterTotal++;
                                }

                                float predForceX = sumNormalX * (thrustVal * firingCount * 9.8f);
                                float predForceY = sumNormalY * (thrustVal * firingCount * 9.8f);
                                double predMassFlow = firingCount > 0f ? (double)thrustVal * firingCount / ispVal : 0.0;

                                totalForceX += predForceX;
                                totalForceY += predForceY;
                                totalMassFlow += predMassFlow;

                                var msb2 = new StringBuilder();
                                msb2.Append("{\"rcsOn\":").Append(rcsOnF ? "true" : "false");
                                msb2.Append(",\"turnAxis\":").Append(Num(turnAxisF));
                                msb2.Append(",\"directionalAxis\":{\"x\":").Append(Num(dirAxisX)).Append(",\"y\":").Append(Num(dirAxisY)).Append("}");
                                msb2.Append(",\"moduleDeadzoned\":").Append(moduleDeadzoned ? "true" : "false");
                                msb2.Append(",\"thrustPositionWorld\":{\"x\":").Append(Num(thrustPosWorldX)).Append(",\"y\":").Append(Num(thrustPosWorldY)).Append("}");
                                msb2.Append(",\"thrusterCount\":").Append(thrusterTotal);
                                msb2.Append(",\"firingCount\":").Append(Num(firingCount));
                                msb2.Append(",\"sumNormal\":{\"x\":").Append(Num(sumNormalX)).Append(",\"y\":").Append(Num(sumNormalY)).Append("}");
                                msb2.Append(",\"predictedForce\":{\"x\":").Append(Num(predForceX)).Append(",\"y\":").Append(Num(predForceY)).Append("}");
                                msb2.Append(",\"predictedMassFlow\":").Append(Num(predMassFlow));
                                msb2.Append(",\"thrusters\":[").Append(string.Join(",", thrusterResults.ToArray())).Append("]");
                                msb2.Append("}");
                                moduleResults.Add(msb2.ToString());
                            }
                        }
                    }

                    var fsb = new StringBuilder();
                    fsb.Append("{\"moduleCount\":").Append(moduleResults.Count);
                    fsb.Append(",\"totalPredictedForce\":{\"x\":").Append(Num(totalForceX)).Append(",\"y\":").Append(Num(totalForceY)).Append("}");
                    fsb.Append(",\"totalPredictedMassFlow\":").Append(Num(totalMassFlow));
                    fsb.Append(",\"rocketMass\":").Append(Num(rocketMass));
                    fsb.Append(",\"worldCenterOfMass\":{\"x\":").Append(Num(comX)).Append(",\"y\":").Append(Num(comY)).Append("}");
                    fsb.Append(",\"modules\":[").Append(string.Join(",", moduleResults.ToArray())).Append("]}");
                    Write("sfs_probe_rcsforce.json", fsb, "rcsforce modules=" + moduleResults.Count);
                    ProbeMod.Result("rcsforce: " + moduleResults.Count + " module(s), totalForce=(" +
                                     totalForceX + "," + totalForceY + ") -> sfs_probe_rcsforce.json" +
                                     (moduleResults.Count == 0 ? " (this rocket has no RCS parts)" : ""));
                    break;
                }

                case "aerotorque":
                {
                    // On-demand version of TryComputeAeroTorque -- see that
                    // function's own header comment (right above GetHeatPartsArray
                    // below) for the two things it does that no earlier command did:
                    // rotating centerOfDrag into real world/scene space, and reading
                    // rb2d.inertia for the first time. NOT valid mid-parachute-
                    // deployment (see that same comment) -- for a real validation
                    // flight, keep the chute stowed.
                    object rAT2 = ActiveRocket();
                    if (rAT2 == null) { ProbeMod.Result("aerotorque: no active rocket"); break; }

                    float torqueZ, alphaPred, fX, fY, copWX, copWY, copAX, copAY, comXo, comYo, inertiaO, dragAO, angularDragO;
                    double densityO;
                    bool torqueOk = TryComputeAeroTorque(rAT2, out torqueZ, out alphaPred, out fX, out fY,
                        out copWX, out copWY, out copAX, out copAY, out comXo, out comYo, out inertiaO, out dragAO, out densityO, out angularDragO);

                    if (!torqueOk)
                    {
                        ProbeMod.Result("aerotorque: FAILED (no drag surfaces exposed, near-zero speed, or a reflection call failed -- see probe.log)");
                        break;
                    }

                    var atsb = new StringBuilder();
                    atsb.Append("{\"dragArea\":").Append(Num(dragAO));
                    atsb.Append(",\"density\":").Append(Num(densityO));
                    atsb.Append(",\"force\":{\"x\":").Append(Num(fX)).Append(",\"y\":").Append(Num(fY)).Append("}");
                    atsb.Append(",\"copWorld\":{\"x\":").Append(Num(copWX)).Append(",\"y\":").Append(Num(copWY)).Append("}");
                    atsb.Append(",\"copApplied\":{\"x\":").Append(Num(copAX)).Append(",\"y\":").Append(Num(copAY)).Append("}");
                    atsb.Append(",\"worldCenterOfMass\":{\"x\":").Append(Num(comXo)).Append(",\"y\":").Append(Num(comYo)).Append("}");
                    atsb.Append(",\"inertia\":").Append(Num(inertiaO));
                    atsb.Append(",\"angularDrag\":").Append(Num(angularDragO));
                    atsb.Append(",\"predictedTorque\":").Append(Num(torqueZ));
                    atsb.Append(",\"predictedAngularAccelDegPerSec2\":").Append(Num(alphaPred * 57.29578f));
                    atsb.Append("}");
                    Write("sfs_probe_aerotorque.json", atsb, "aerotorque dump");
                    ProbeMod.Result("aerotorque: torque=" + torqueZ + " inertia=" + inertiaO +
                                     " predAlpha=" + (alphaPred * 57.29578f) + "deg/s^2 -> sfs_probe_aerotorque.json");
                    break;
                }

                case "gimbalinfo":
                {
                    // Confirms the full commanded-steering -> gimbal-angle chain
                    // (all three pieces read via IL 2026-08-31):
                    //   EngineModule.RecalculateGimbal writes
                    //     gimbal.targetTime = turnAxis_Input * RotationDirection(transform)
                    //     every frame the engine has thrust > 0 (else 0).
                    //   MoveModule.Update chases that target LINEARLY via
                    //     Mathf.MoveTowards at rate 1/animationTime -- no easing,
                    //     no spring-damping, reaches target in exactly
                    //     animationTime seconds.
                    //   MoveModule.ApplyAnimation sets the real angle from
                    //     transform.localEulerAngles.z = X.Evaluate(time - offset)
                    //     for the type==0 (Rotate) animationElements entry, where
                    //     X is a Unity AnimationCurve (keyframe spline).
                    // The one thing IL alone can't answer: whether a REAL engine's
                    // X curve is a plain 2-key linear ramp or has easing baked in.
                    // This command dumps the live curve keyframes so that's
                    // answerable directly, plus every other piece of the chain in
                    // one place for a real steering-input validation flight.
                    object rGI = ActiveRocket();
                    if (rGI == null) { ProbeMod.Result("gimbalinfo: no active rocket"); break; }
                    object holderGI = Get(rGI, "partHolder");
                    object partsGI = Get(holderGI, "parts");
                    var enGI = partsGI as System.Collections.IEnumerable;
                    var gimbalResults = new List<string>();
                    if (enGI != null)
                    {
                        foreach (object part in enGI)
                        {
                            string pname = "?";
                            try { pname = (string)Get(Get(part, "displayName"), "TranslatableName"); } catch { }
                            foreach (object mv in ModuleValues(part))
                            {
                                if (mv.GetType().Name != "EngineModule") continue;
                                try
                                {
                                    bool hasGimbal = ToB(Get(mv, "hasGimbal"));
                                    if (!hasGimbal) continue;

                                    bool gimbalOn = ToB(GetWrapped2(Get(mv, "gimbalOn")));
                                    float throttleOut = ToF(GetWrapped2(Get(mv, "throttle_Out")));
                                    float turnAxisInput = ToF(GetWrapped2(Get(mv, "turnAxis_Input")));

                                    object gimbal = Get(mv, "gimbal");   // the MoveModule
                                    float timeVal = ToF(GetWrapped2(Get(gimbal, "time")));
                                    float targetTimeVal = ToF(GetWrapped2(Get(gimbal, "targetTime")));
                                    float animationTime = ToF(Get(gimbal, "animationTime"));
                                    bool unscaledTime = ToB(Get(gimbal, "unscaledTime"));

                                    var gsb = new StringBuilder();
                                    gsb.Append("{\"part\":").Append(Q(pname));
                                    gsb.Append(",\"gimbalOn\":").Append(gimbalOn ? "true" : "false");
                                    gsb.Append(",\"throttleOut\":").Append(Num(throttleOut));
                                    gsb.Append(",\"turnAxisInput\":").Append(Num(turnAxisInput));
                                    gsb.Append(",\"time\":").Append(Num(timeVal));
                                    gsb.Append(",\"targetTime\":").Append(Num(targetTimeVal));
                                    gsb.Append(",\"animationTime\":").Append(Num(animationTime));
                                    gsb.Append(",\"unscaledTime\":").Append(unscaledTime ? "true" : "false");

                                    // Dump the rotate-type (type==0) curve's keyframes, if any --
                                    // confirmed as index 0 in MoveModule.ApplyAnimation's switch.
                                    object elements = Get(gimbal, "animationElements");
                                    var elEn = elements as System.Collections.IEnumerable;
                                    var curveKeys = new List<string>();
                                    if (elEn != null)
                                    {
                                        foreach (object el in elEn)
                                        {
                                            object typeObj = Get(el, "type");
                                            int typeIdx = typeObj == null ? -1 : Convert.ToInt32(typeObj);
                                            if (typeIdx != 0) continue;
                                            float offset = ToF(Get(el, "offset"));
                                            object curve = Get(el, "X");
                                            if (curve == null) continue;
                                            object keysObj = Get(curve, "keys");
                                            var keysArr = keysObj as System.Collections.IEnumerable;
                                            if (keysArr == null) continue;
                                            var ksb = new StringBuilder();
                                            ksb.Append("{\"offset\":").Append(Num(offset)).Append(",\"keys\":[");
                                            bool first = true;
                                            foreach (object kf in keysArr)
                                            {
                                                if (!first) ksb.Append(",");
                                                first = false;
                                                float kt = ToF(Get(kf, "time"));
                                                float kv = ToF(Get(kf, "value"));
                                                float kin = ToF(Get(kf, "inTangent"));
                                                float kout = ToF(Get(kf, "outTangent"));
                                                ksb.Append("{\"t\":").Append(Num(kt))
                                                   .Append(",\"v\":").Append(Num(kv))
                                                   .Append(",\"in\":").Append(Num(kin))
                                                   .Append(",\"out\":").Append(Num(kout))
                                                   .Append("}");
                                            }
                                            ksb.Append("]}");
                                            curveKeys.Add(ksb.ToString());
                                        }
                                    }
                                    gsb.Append(",\"rotateCurves\":[").Append(string.Join(",", curveKeys.ToArray())).Append("]");
                                    gsb.Append("}");
                                    gimbalResults.Add(gsb.ToString());
                                }
                                catch (Exception e)
                                {
                                    ProbeMod.Log("[gimbalinfo] EngineModule read error on part \"" + pname + "\": " + e.Message);
                                    gimbalResults.Add("{\"part\":" + Q(pname) + ",\"error\":" + Q(e.Message) + "}");
                                }
                            }
                        }
                    }
                    if (gimbalResults.Count == 0)
                    {
                        ProbeMod.Result("gimbalinfo: no gimbaling engines found on active rocket (hasGimbal false on all engines)");
                        break;
                    }
                    var gAll = new StringBuilder();
                    gAll.Append("[").Append(string.Join(",", gimbalResults.ToArray())).Append("]");
                    Write("sfs_probe_gimbalinfo.json", gAll, "gimbalinfo dump");
                    ProbeMod.Result("gimbalinfo: " + gimbalResults.Count + " gimbaling engine(s) -> sfs_probe_gimbalinfo.json");
                    break;
                }

                case "getforwardstartinfo":
                {
                    // Captures everything forward_sim.py's craft_config needs
                    // to predict THIS EXACT rocket's future motion from real
                    // per-part specs (thrust/ISP/geometry/thresholds/curves),
                    // read live via reflection -- not an empirical fit, the
                    // same way every other confirmed-formula command in this
                    // file works. Call this BEFORE ignition (throttle=0,
                    // gimbal undeflected) for the cleanest read -- engine
                    // thrustNormal reflects CURRENT gimbal deflection if any
                    // is active at capture time (backed out below using the
                    // live gimbal.time reading and the confirmed linear
                    // MoveModule model, B1.10, but a zero-deflection capture
                    // needs no backing-out and is strictly more reliable).
                    //
                    // KNOWN SCOPE LIMITS, not silently glossed over:
                    // - dragArea(AoA) is NOT captured here -- that needs
                    //   either a full flight (analysis/aoa_dragarea.py's
                    //   existing empirical-table approach) or real per-part
                    //   exposed-surface geometry this command doesn't read.
                    //   Use the AoA table tool for that piece separately.
                    // - Engine "scale" (RecalculateMassFlow's world-transform
                    //   magnitude term, D2.3) is defaulted to 1.0 here --
                    //   exact for any unscaled part (the common case). A
                    //   genuinely scaled engine part would need this read
                    //   properly; flagged, not silently assumed away.
                    // - position_local is captured in the rocket's CURRENT
                    //   configuration -- valid as a body-fixed offset going
                    //   forward ONLY until the next staging event changes
                    //   which parts remain. This is a snapshot of the
                    //   CURRENT config, not a schedule of every future
                    //   stage's config. Re-run after each real staging event
                    //   for a multi-stage prediction that spans separations.
                    object rFS = ActiveRocket();
                    if (rFS == null) { ProbeMod.Result("getforwardstartinfo: no active rocket"); break; }
                    object rb2dFS = Get(rFS, "rb2d");
                    if (rb2dFS == null) { ProbeMod.Result("getforwardstartinfo: no rb2d"); break; }
                    object comObjFS = Get(rb2dFS, "worldCenterOfMass");
                    if (comObjFS == null) { ProbeMod.Result("getforwardstartinfo: worldCenterOfMass read failed"); break; }
                    float comX = ToF(Get(comObjFS, "x"));
                    float comY = ToF(Get(comObjFS, "y"));
                    double rocketMassFS = ToD(Get(rb2dFS, "mass"));
                    float inertiaFS = ToF(Get(rb2dFS, "inertia"));
                    float rotationDegFS = ToF(Get(rb2dFS, "rotation"));

                    // part -> stageId map, same live mapping FuelByStage uses.
                    var partStageMap = new Dictionary<object, int>(ReferenceEqualityComparer.Instance);
                    try
                    {
                        object stagingFS = Get(rFS, "staging");
                        object stagesFS = Get(stagingFS, "stages");
                        var stagesEn = stagesFS as System.Collections.IEnumerable;
                        if (stagesEn != null)
                        {
                            foreach (object stage in stagesEn)
                            {
                                int sid = (int)Get(stage, "stageId");
                                object stageParts = Get(stage, "parts");
                                var spEn = stageParts as System.Collections.IEnumerable;
                                if (spEn == null) continue;
                                foreach (object p in spEn) partStageMap[p] = sid;
                            }
                        }
                    }
                    catch (Exception e) { ProbeMod.Log("[getforwardstartinfo] stage map error: " + e.Message); }

                    object holderFS = Get(rFS, "partHolder");
                    object partsFS = Get(holderFS, "parts");
                    var partsEnFS = partsFS as System.Collections.IEnumerable;

                    var engineResults = new List<string>();
                    var rcsResults = new List<string>();
                    var chuteResults = new List<string>();
                    var torqueModuleResults = new List<string>();
                    double torqueEffectiveRaw = 0.0;

                    Type v3CacheFS = null;
                    MethodInfo vec2to3FS = null;
                    MethodInfo transformPointFS = null;

                    if (partsEnFS != null)
                    {
                        foreach (object part in partsEnFS)
                        {
                            string pname = "?";
                            try { pname = (string)Get(Get(part, "displayName"), "TranslatableName"); } catch { }
                            int stageIdFS;
                            string stageStr = partStageMap.TryGetValue(part, out stageIdFS) ? stageIdFS.ToString() : "null";
                            object partTransform = null;
                            try { partTransform = Get(part, "transform"); } catch { }

                            foreach (object mv in ModuleValues(part))
                            {
                                string typeName = mv.GetType().Name;

                                if (typeName == "EngineModule")
                                {
                                    try
                                    {
                                        float thrustTon = ToF(GetWrapped2(Get(mv, "thrust")));
                                        float ispV = ToF(GetWrapped2(Get(mv, "ISP")));
                                        object thrustPosRefFS = Get(mv, "thrustPosition");
                                        float posLocalPartX = ToF(GetWrapped2(Get(thrustPosRefFS, "x")));
                                        float posLocalPartY = ToF(GetWrapped2(Get(thrustPosRefFS, "y")));
                                        object thrustNormRefFS = Get(mv, "thrustNormal");
                                        float dirLocalX = ToF(GetWrapped2(Get(thrustNormRefFS, "x")));
                                        float dirLocalY = ToF(GetWrapped2(Get(thrustNormRefFS, "y")));

                                        bool hasGimbalFS = ToB(Get(mv, "hasGimbal"));
                                        float gimbalRangeDeg = 0f;
                                        float animationTimeS = 0f;
                                        if (hasGimbalFS)
                                        {
                                            object gimbalFS = Get(mv, "gimbal");
                                            float gimbalTimeNow = ToF(GetWrapped2(Get(gimbalFS, "time")));
                                            animationTimeS = ToF(Get(gimbalFS, "animationTime"));
                                            object elementsFS = Get(gimbalFS, "animationElements");
                                            var elEnFS = elementsFS as System.Collections.IEnumerable;
                                            float maxAbsV = 0f;
                                            if (elEnFS != null)
                                            {
                                                foreach (object el in elEnFS)
                                                {
                                                    object typeObj = Get(el, "type");
                                                    int typeIdx = typeObj == null ? -1 : Convert.ToInt32(typeObj);
                                                    if (typeIdx != 0) continue;
                                                    object curve = Get(el, "X");
                                                    if (curve == null) continue;
                                                    object keysObj = Get(curve, "keys");
                                                    var keysArr = keysObj as System.Collections.IEnumerable;
                                                    if (keysArr == null) continue;
                                                    foreach (object kf in keysArr)
                                                    {
                                                        float kv = Math.Abs(ToF(Get(kf, "value")));
                                                        if (kv > maxAbsV) maxAbsV = kv;
                                                    }
                                                }
                                            }
                                            gimbalRangeDeg = maxAbsV;
                                            float deflectionNowDeg = gimbalTimeNow * gimbalRangeDeg;
                                            double undoRad = -deflectionNowDeg * Math.PI / 180.0;
                                            double cu = Math.Cos(undoRad), su = Math.Sin(undoRad);
                                            float baseX = (float)(dirLocalX * cu - dirLocalY * su);
                                            float baseY = (float)(dirLocalX * su + dirLocalY * cu);
                                            dirLocalX = baseX; dirLocalY = baseY;
                                        }

                                        object vec2LocalEng = MakeVector2Like(comObjFS, posLocalPartX, posLocalPartY);
                                        float worldOffX, worldOffY;
                                        bool posOk = TryTransformPointToWorld(partTransform, vec2LocalEng,
                                            ref v3CacheFS, ref vec2to3FS, ref transformPointFS, out worldOffX, out worldOffY);
                                        string posLocalBodyStr = "null";
                                        if (posOk)
                                        {
                                            worldOffX -= comX; worldOffY -= comY;
                                            float lx, ly;
                                            WorldOffsetToBodyLocal(worldOffX, worldOffY, rotationDegFS, out lx, out ly);
                                            posLocalBodyStr = "{\"x\":" + Num(lx) + ",\"y\":" + Num(ly) + "}";
                                        }

                                        var esb = new StringBuilder();
                                        esb.Append("{\"part\":").Append(Q(pname));
                                        esb.Append(",\"stage\":").Append(stageStr);
                                        esb.Append(",\"thrustTon\":").Append(Num(thrustTon));
                                        esb.Append(",\"isp\":").Append(Num(ispV));
                                        esb.Append(",\"scale\":1.0");
                                        esb.Append(",\"hasGimbal\":").Append(hasGimbalFS ? "true" : "false");
                                        esb.Append(",\"gimbalRangeDeg\":").Append(hasGimbalFS ? Num(gimbalRangeDeg) : "null");
                                        esb.Append(",\"animationTimeS\":").Append(hasGimbalFS ? Num(animationTimeS) : "null");
                                        esb.Append(",\"positionLocalBody\":").Append(posLocalBodyStr);
                                        esb.Append(",\"baseDirectionLocal\":{\"x\":").Append(Num(dirLocalX)).Append(",\"y\":").Append(Num(dirLocalY)).Append("}");
                                        esb.Append("}");
                                        engineResults.Add(esb.ToString());
                                    }
                                    catch (Exception e)
                                    {
                                        ProbeMod.Log("[getforwardstartinfo] EngineModule error on \"" + pname + "\": " + e.Message);
                                        engineResults.Add("{\"part\":" + Q(pname) + ",\"error\":" + Q(e.Message) + "}");
                                    }
                                }
                                else if (typeName == "RcsModule")
                                {
                                    try
                                    {
                                        float thrustTonR = ToF(Get(mv, "thrust"));
                                        float ispR = ToF(Get(mv, "ISP"));
                                        float dAngle = ToF(Get(mv, "directionAngleThreshold"));
                                        float tAngle = ToF(Get(mv, "torqueAngleThreshold"));
                                        object thrustPosR = Get(mv, "thrustPosition");

                                        float worldOffX, worldOffY;
                                        bool posOk = TryTransformPointToWorld(partTransform, thrustPosR,
                                            ref v3CacheFS, ref vec2to3FS, ref transformPointFS, out worldOffX, out worldOffY);
                                        string posLocalBodyStr = "null";
                                        if (posOk)
                                        {
                                            worldOffX -= comX; worldOffY -= comY;
                                            float lx, ly;
                                            WorldOffsetToBodyLocal(worldOffX, worldOffY, rotationDegFS, out lx, out ly);
                                            posLocalBodyStr = "{\"x\":" + Num(lx) + ",\"y\":" + Num(ly) + "}";
                                        }

                                        var normalsList = new List<string>();
                                        object thrustersR = Get(mv, "thrusters");
                                        var thEnR = thrustersR as System.Collections.IEnumerable;
                                        int thrusterCountR = 0;
                                        if (thEnR != null)
                                        {
                                            foreach (object th in thEnR)
                                            {
                                                thrusterCountR++;
                                                object normalObj = Get(th, "thrustNormal");
                                                float nx = ToF(Get(normalObj, "x"));
                                                float ny = ToF(Get(normalObj, "y"));
                                                normalsList.Add("{\"x\":" + Num(nx) + ",\"y\":" + Num(ny) + "}");
                                            }
                                        }

                                        var rsb = new StringBuilder();
                                        rsb.Append("{\"part\":").Append(Q(pname));
                                        rsb.Append(",\"stage\":").Append(stageStr);
                                        rsb.Append(",\"thrustTon\":").Append(Num(thrustTonR));
                                        rsb.Append(",\"isp\":").Append(Num(ispR));
                                        rsb.Append(",\"directionAngleThreshold\":").Append(Num(dAngle));
                                        rsb.Append(",\"torqueAngleThreshold\":").Append(Num(tAngle));
                                        rsb.Append(",\"positionLocalBody\":").Append(posLocalBodyStr);
                                        rsb.Append(",\"thrusterCount\":").Append(thrusterCountR);
                                        rsb.Append(",\"thrusterNormals\":[").Append(string.Join(",", normalsList.ToArray())).Append("]");
                                        rsb.Append("}");
                                        rcsResults.Add(rsb.ToString());
                                    }
                                    catch (Exception e)
                                    {
                                        ProbeMod.Log("[getforwardstartinfo] RcsModule error on \"" + pname + "\": " + e.Message);
                                        rcsResults.Add("{\"part\":" + Q(pname) + ",\"error\":" + Q(e.Message) + "}");
                                    }
                                }
                                else if (typeName == "ParachuteModule")
                                {
                                    try
                                    {
                                        double maxDeployH = ToD(GetWrapped2(Get(mv, "maxDeployHeight")));
                                        double maxDeployV = ToD(GetWrapped2(Get(mv, "maxDeployVelocity")));
                                        object chuteTransform = Get(mv, "parachute");
                                        float posLocalBodyX = 0f, posLocalBodyY = 0f;
                                        bool posOk = false;
                                        if (chuteTransform != null)
                                        {
                                            object worldPosObj = Get(chuteTransform, "position");
                                            if (worldPosObj != null)
                                            {
                                                float wx = ToF(Get(worldPosObj, "x"));
                                                float wy = ToF(Get(worldPosObj, "y"));
                                                wx -= comX; wy -= comY;
                                                WorldOffsetToBodyLocal(wx, wy, rotationDegFS, out posLocalBodyX, out posLocalBodyY);
                                                posOk = true;
                                            }
                                        }

                                        var curveKeys = new List<string>();
                                        object curveObj = Get(mv, "drag");
                                        if (curveObj != null)
                                        {
                                            object keysObj = Get(curveObj, "keys");
                                            var keysArr = keysObj as System.Collections.IEnumerable;
                                            if (keysArr != null)
                                            {
                                                foreach (object kf in keysArr)
                                                {
                                                    float kt = ToF(Get(kf, "time"));
                                                    float kv = ToF(Get(kf, "value"));
                                                    float kin = ToF(Get(kf, "inTangent"));
                                                    float kout = ToF(Get(kf, "outTangent"));
                                                    curveKeys.Add("{\"t\":" + Num(kt) + ",\"v\":" + Num(kv) + ",\"in\":" + Num(kin) + ",\"out\":" + Num(kout) + "}");
                                                }
                                            }
                                        }

                                        var psb = new StringBuilder();
                                        psb.Append("{\"part\":").Append(Q(pname));
                                        psb.Append(",\"stage\":").Append(stageStr);
                                        psb.Append(",\"maxDeployHeight\":").Append(Num(maxDeployH));
                                        psb.Append(",\"maxDeployVelocity\":").Append(Num(maxDeployV));
                                        psb.Append(",\"positionLocalBody\":").Append(posOk ? ("{\"x\":" + Num(posLocalBodyX) + ",\"y\":" + Num(posLocalBodyY) + "}") : "null");
                                        psb.Append(",\"dragCurveKeys\":[").Append(string.Join(",", curveKeys.ToArray())).Append("]");
                                        psb.Append("}");
                                        chuteResults.Add(psb.ToString());
                                    }
                                    catch (Exception e)
                                    {
                                        ProbeMod.Log("[getforwardstartinfo] ParachuteModule error on \"" + pname + "\": " + e.Message);
                                        chuteResults.Add("{\"part\":" + Q(pname) + ",\"error\":" + Q(e.Message) + "}");
                                    }
                                }
                                else if (typeName == "TorqueModule")
                                {
                                    try
                                    {
                                        object enabledRef = Get(mv, "enabled");
                                        bool isLocal = ToB(Get(enabledRef, "Local"));
                                        bool valueField = ToB(GetWrapped2(enabledRef));
                                        bool isEnabledTM = isLocal || valueField;
                                        float torqueVal = ToF(GetWrapped2(Get(mv, "torque")));
                                        if (isEnabledTM) torqueEffectiveRaw += torqueVal;
                                        torqueModuleResults.Add("{\"part\":" + Q(pname) + ",\"stage\":" + stageStr +
                                            ",\"torque\":" + Num(torqueVal) + ",\"enabled\":" + (isEnabledTM ? "true" : "false") + "}");
                                    }
                                    catch (Exception e)
                                    {
                                        ProbeMod.Log("[getforwardstartinfo] TorqueModule error on \"" + pname + "\": " + e.Message);
                                    }
                                }
                            }
                        }
                    }

                    var fsOut = new StringBuilder();
                    fsOut.Append("{\"mass\":").Append(Num(rocketMassFS));
                    fsOut.Append(",\"inertia\":").Append(Num(inertiaFS));
                    fsOut.Append(",\"worldCenterOfMass\":{\"x\":").Append(Num(comX)).Append(",\"y\":").Append(Num(comY)).Append("}");
                    fsOut.Append(",\"rotationDeg\":").Append(Num(rotationDegFS));
                    fsOut.Append(",\"torqueEffectiveRaw\":").Append(Num(torqueEffectiveRaw));
                    fsOut.Append(",\"torqueModules\":[").Append(string.Join(",", torqueModuleResults.ToArray())).Append("]");
                    fsOut.Append(",\"engines\":[").Append(string.Join(",", engineResults.ToArray())).Append("]");
                    fsOut.Append(",\"rcsModules\":[").Append(string.Join(",", rcsResults.ToArray())).Append("]");
                    fsOut.Append(",\"parachutes\":[").Append(string.Join(",", chuteResults.ToArray())).Append("]");
                    fsOut.Append("}");
                    Write("sfs_probe_forwardstartinfo.json", fsOut, "forward-integrator craft config dump");

                    // 2026-09-06: ALSO write a full 0.5-degree-resolution AoA drag
                    // table for this exact craft, every time getforwardstartinfo runs
                    // -- so a fresh table always exists alongside the fresh craft
                    // config snapshot, one per blueprint (by name), no separate
                    // command needed. Same TryComputeDragAreaAtAoA mechanism as the
                    // standalone 'dragareasweep' command, just always run at full
                    // resolution (721 samples, -180.0 to 180.0 inclusive by 0.5) and
                    // auto-named from the rocket's real blueprint name so re-running
                    // this for a DIFFERENT craft never silently overwrites a
                    // different craft's table under the same generic filename.
                    object rocketNameObjFS = null;
                    string blueprintNameFS = "unknown";
                    string aoaTableFileName = "AoA_drag_table_unknown.json";
                    int aoaSampleCountFS = 0;
                    try
                    {
                        // 2026-09-06: an optional caller-supplied name (e.g.
                        // "getforwardstartinfo one_engine_gimbal_test") takes
                        // priority over the real Rocket.rocketName. Added because
                        // rocketName is genuinely blank for any craft that hasn't
                        // been named+launched yet -- by the time it CAN be named,
                        // naming it is no longer useful for this workflow (you're
                        // already past the pre-ignition snapshot moment this
                        // command is meant to be called at). No spaces in the name
                        // (matches this file's existing single-arg convention, e.g.
                        // dragareasweep's angle list).
                        if (!string.IsNullOrEmpty(arg))
                        {
                            blueprintNameFS = arg;
                        }
                        else
                        {
                            rocketNameObjFS = Get(rFS, "rocketName");
                            blueprintNameFS = rocketNameObjFS != null ? rocketNameObjFS.ToString() : "unknown";
                        }
                        var safeNameSb = new StringBuilder();
                        foreach (char c in blueprintNameFS)
                            safeNameSb.Append((char.IsLetterOrDigit(c) || c == '_' || c == '-') ? c : '_');
                        string safeBlueprintName = safeNameSb.Length > 0 ? safeNameSb.ToString() : "unknown";

                        var aoaResultsFS = new List<string>();
                        for (float aoaDegFS = -180f; aoaDegFS <= 180f + 0.001f; aoaDegFS += 0.5f)
                        {
                            float aoaSweepDrag, aoaSweepCopX, aoaSweepCopY;
                            int aoaSweepAllCount, aoaSweepExposedCount;
                            bool aoaSweepOk = TryComputeDragAreaAtAoA(rFS, aoaDegFS, out aoaSweepDrag, out aoaSweepCopX, out aoaSweepCopY,
                                out aoaSweepAllCount, out aoaSweepExposedCount);
                            var aoaSsb = new StringBuilder();
                            aoaSsb.Append("{\"aoaDeg\":").Append(Num(aoaDegFS));
                            aoaSsb.Append(",\"dragArea\":").Append(aoaSweepOk ? Num(aoaSweepDrag) : "null");
                            aoaSsb.Append(",\"dragCopX\":").Append(aoaSweepOk ? Num(aoaSweepCopX) : "null");
                            aoaSsb.Append(",\"dragCopY\":").Append(aoaSweepOk ? Num(aoaSweepCopY) : "null");
                            aoaSsb.Append("}");
                            aoaResultsFS.Add(aoaSsb.ToString());
                        }
                        var aoaTableOut = new StringBuilder();
                        aoaTableOut.Append("{\"blueprintName\":").Append(Q(blueprintNameFS));
                        aoaTableOut.Append(",\"realRotationDeg\":").Append(Num(rotationDegFS));
                        aoaTableOut.Append(",\"stepDeg\":0.5");
                        aoaTableOut.Append(",\"note\":\"dragCopX/Y are in the same velocity-aligned frame as computed:dragArea's dragCopX/Y -- NOT world/local frame\"");
                        aoaTableOut.Append(",\"samples\":[").Append(string.Join(",", aoaResultsFS.ToArray())).Append("]}");
                        aoaTableFileName = "AoA_drag_table_" + safeBlueprintName + ".json";
                        aoaSampleCountFS = aoaResultsFS.Count;
                        Write(aoaTableFileName, aoaTableOut, "full-resolution AoA drag table for this craft");
                    }
                    catch (Exception e)
                    {
                        ProbeMod.Log("[getforwardstartinfo] AoA drag table sweep FAILED (craft config above was still written fine): " + e);
                        aoaTableFileName = null;
                    }

                    ProbeMod.Result("getforwardstartinfo: " + engineResults.Count + " engine(s), " + rcsResults.Count +
                        " RCS module(s), " + chuteResults.Count + " parachute(s), " + torqueModuleResults.Count +
                        " torque module(s) (raw sum=" + torqueEffectiveRaw + ") -> sfs_probe_forwardstartinfo.json; " +
                        (aoaTableFileName != null ? (aoaSampleCountFS + "-sample AoA drag table -> " + aoaTableFileName) : "AoA drag table FAILED, see probe.log"));
                    break;
                }

                case "parachutedrag":
                {
                    // On-demand version of TryComputeParachuteDrag -- see that
                    // function's header comment for the confirmed compounding
                    // logic. Returns 'chutesActive:0' harmlessly if no chute is
                    // currently deployed (targetState 1 or 2) -- the prediction
                    // then just reduces to the plain aero-torque case.
                    object rPD = ActiveRocket();
                    if (rPD == null) { ProbeMod.Result("parachutedrag: no active rocket"); break; }

                    float pdTorque, pdAlpha, pdFx, pdFy, pdCopX, pdCopY, pdComX, pdComY, pdInertia, pdDragArea, pdChuteDrag;
                    int pdNumChutes;
                    bool pdOk = TryComputeParachuteDrag(rPD, out pdTorque, out pdAlpha, out pdFx, out pdFy,
                        out pdCopX, out pdCopY, out pdComX, out pdComY, out pdInertia, out pdDragArea,
                        out pdChuteDrag, out pdNumChutes);

                    if (!pdOk)
                    {
                        ProbeMod.Result("parachutedrag: FAILED (no drag surfaces exposed, near-zero speed, or a reflection call failed -- see probe.log)");
                        break;
                    }

                    var pdsb = new StringBuilder();
                    pdsb.Append("{\"dragArea\":").Append(Num(pdDragArea));
                    pdsb.Append(",\"chutesActive\":").Append(pdNumChutes);
                    pdsb.Append(",\"chuteDragTotal\":").Append(Num(pdChuteDrag));
                    pdsb.Append(",\"force\":{\"x\":").Append(Num(pdFx)).Append(",\"y\":").Append(Num(pdFy)).Append("}");
                    pdsb.Append(",\"copApplied\":{\"x\":").Append(Num(pdCopX)).Append(",\"y\":").Append(Num(pdCopY)).Append("}");
                    pdsb.Append(",\"worldCenterOfMass\":{\"x\":").Append(Num(pdComX)).Append(",\"y\":").Append(Num(pdComY)).Append("}");
                    pdsb.Append(",\"inertia\":").Append(Num(pdInertia));
                    pdsb.Append(",\"predictedTorque\":").Append(Num(pdTorque));
                    pdsb.Append(",\"predictedAngularAccelDegPerSec2\":").Append(Num(pdAlpha * 57.29578f));
                    pdsb.Append("}");
                    Write("sfs_probe_parachutedrag.json", pdsb, "parachutedrag dump");
                    ProbeMod.Result("parachutedrag: chutesActive=" + pdNumChutes + " chuteDrag=" + pdChuteDrag +
                                     " torque=" + pdTorque + " predAlpha=" + (pdAlpha * 57.29578f) + "deg/s^2 -> sfs_probe_parachutedrag.json");
                    break;
                }

                case "assignkey":
                {
                    // "assignkey <key> <command...>" -- binds a key so the
                    // PLAYER can trigger a probe command at the exact moment
                    // only they know is right (e.g. "the instant I hit full
                    // deflection"), rather than Claude reacting a beat late
                    // to typed narration. The target command runs through the
                    // normal Command() dispatch, so anything callable via
                    // command.txt is bindable, including commands with their
                    // own args (e.g. "assignkey - terrain -10,0,10").
                    int firstSpaceAK = line.IndexOf(' ');
                    string afterCmdAK = firstSpaceAK >= 0 ? line.Substring(firstSpaceAK + 1).TrimStart() : "";
                    int secondSpaceAK = afterCmdAK.IndexOf(' ');
                    if (secondSpaceAK < 0)
                    {
                        ProbeMod.Result("assignkey: need a key and a command, e.g. 'assignkey - rcsforce'");
                        break;
                    }
                    string keyStrAK = afterCmdAK.Substring(0, secondSpaceAK);
                    string targetCmdAK = afterCmdAK.Substring(secondSpaceAK + 1).Trim();
                    if (targetCmdAK.Length == 0)
                    {
                        ProbeMod.Result("assignkey: empty target command");
                        break;
                    }
                    KeyCode? kcAK = ParseKeyCode(keyStrAK);
                    if (kcAK == null)
                    {
                        ProbeMod.Result("assignkey: unrecognized key '" + keyStrAK + "'");
                        break;
                    }
                    KeyBindings[kcAK.Value] = targetCmdAK;
                    ProbeMod.Result("assignkey: '" + keyStrAK + "' (" + kcAK.Value + ") -> '" + targetCmdAK +
                                     "'  (" + KeyBindings.Count + " binding(s) active)");
                    break;
                }

                case "unassignkey":
                {
                    if (string.IsNullOrEmpty(arg))
                    {
                        ProbeMod.Result("unassignkey: need a key, e.g. 'unassignkey -'");
                        break;
                    }
                    KeyCode? kcUK = ParseKeyCode(arg);
                    if (kcUK == null)
                    {
                        ProbeMod.Result("unassignkey: unrecognized key '" + arg + "'");
                        break;
                    }
                    bool removedUK = KeyBindings.Remove(kcUK.Value);
                    ProbeMod.Result("unassignkey: '" + arg + "' " + (removedUK ? "removed" : "was not bound") +
                                     "  (" + KeyBindings.Count + " binding(s) active)");
                    break;
                }

                case "listkeys":
                {
                    var lkParts = new List<string>();
                    foreach (var kv in KeyBindings)
                        lkParts.Add("{\"key\":" + Q(kv.Key.ToString()) + ",\"command\":" + Q(kv.Value) + "}");
                    ProbeMod.Result("listkeys: " + KeyBindings.Count + " binding(s): [" +
                                     string.Join(",", lkParts.ToArray()) + "]");
                    break;
                }

                case "clearkeys":
                {
                    int nCK = KeyBindings.Count;
                    KeyBindings.Clear();
                    ProbeMod.Result("clearkeys: removed " + nCK + " binding(s)");
                    break;
                }

                case "airtemp":
                {
                    // Cheap on-demand diagnostic: single real-time read of
                    // AeroModule.GetTemperatureAndShockwave's actual output for
                    // the current rocket, without needing to be recording
                    // telemetry at all. The per-tick 'realAirTemp' field in
                    // truth.jsonl (added same session) uses this exact same
                    // helper -- use this command for a quick spot-check, use
                    // the telemetry field for a full-flight comparison against
                    // the Python air-temperature formula.
                    object rAT = ActiveRocket();
                    if (rAT == null) { ProbeMod.Result("airtemp: no active rocket"); break; }
                    float realTemp = GetRealAirTemperature(rAT);
                    if (float.IsNaN(realTemp))
                    {
                        ProbeMod.Result("airtemp: FAILED reason=read_error (see probe.log)");
                        break;
                    }
                    ProbeMod.Result("airtemp: " + realTemp + " (real game value, straight from AeroModule.GetTemperatureAndShockwave)");
                    break;
                }

                case "telemetrysnapshot":
                {
                    // Corrected 2026-08-30 (v0.42.0's first version copied the
                    // accumulated FILES, which wasn't what was actually wanted).
                    // This is a genuine one-tick READ: builds exactly the same
                    // inputs/truth JSON a real recorded sample would contain (via
                    // the SAME BuildInputsSample/BuildTruthSample functions
                    // Sample() itself uses, so it can never silently drift from
                    // real telemetry's schema), but does NOT touch Telemetry
                    // state, sampleCount, or either file. Works identically
                    // whether continuous recording is currently on, off, or
                    // already running -- a pure peek, zero interruption either way.
                    //
                    // SCOPED MODE (v0.63.0, 2026-09-06): optional comma-separated
                    // field list, e.g. 'telemetrysnapshot rb2d.angularDrag,rb2d.inertia'
                    // -- same syntax as dragareasweep's arg. Added specifically so a
                    // quick ad-hoc field check doesn't need a full 'telemetry on' /
                    // 'telemetry off' round trip (which writes/archives a real file
                    // just to peek at one or two values). Reuses BuildScopedSample(),
                    // the SAME field-resolution logic real scoped recording uses
                    // (computed:, partCount, plain dot-paths) -- can't silently
                    // diverge from what a real recorded flight would show for the
                    // same field list. No arg = unchanged full inputs+truth dump,
                    // exactly the pre-v0.63.0 behavior, so every existing caller
                    // keeps working unmodified.
                    object rPeek = ActiveRocket();
                    if (rPeek == null) { ProbeMod.Result("telemetrysnapshot: no active rocket"); break; }
                    object rbPeek = Get(rPeek, "rb2d");
                    object locPeek = Unwrap(Get(rPeek, "location"));
                    double tPeek = ToD(Get(locPeek, "time"));

                    if (!string.IsNullOrEmpty(arg))
                    {
                        string[] peekFields = arg.Split(',');
                        string scopedPeek = BuildScopedSample(rPeek, tPeek, peekFields);
                        Write("sfs_probe_telemetry_snapshot.json", new StringBuilder(scopedPeek),
                              "telemetrysnapshot (scoped) t=" + tPeek);
                        ProbeMod.Result("telemetrysnapshot: t=" + tPeek + " scoped[" + peekFields.Length +
                                         "] recording=" + (Telemetry ? "ON" : "off") +
                                         " (not affected either way) -> sfs_probe_telemetry_snapshot.json");
                        break;
                    }

                    string inputsPeek = BuildInputsSample(rPeek, rbPeek, tPeek);
                    string truthPeek = BuildTruthSample(rPeek, rbPeek, locPeek, tPeek);

                    var peekSb = new StringBuilder();
                    peekSb.Append("{\"inputs\":").Append(inputsPeek);
                    peekSb.Append(",\"truth\":").Append(truthPeek);
                    peekSb.Append("}");
                    Write("sfs_probe_telemetry_snapshot.json", peekSb, "telemetrysnapshot t=" + tPeek);
                    ProbeMod.Result("telemetrysnapshot: t=" + tPeek + " recording=" + (Telemetry ? "ON" : "off") +
                                     " (not affected either way) -> sfs_probe_telemetry_snapshot.json");
                    break;
                }

                case "cheat":
                {
                    // FIXED (2026-08-29, Step 1.5 audit findings 1-4):
                    //
                    // Finding 1 -- was: FindComponent("SFS.World.SandboxSettings"),
                    // which resolves via Resources.FindObjectsOfTypeAll(t)[0].
                    // That call can return INACTIVE objects/prefabs in unspecified
                    // order -- if [0] wasn't the live component, the toggle flipped
                    // a detached Data object, but OnToggle() saves the GLOBAL
                    // Base.worldBase.settings (not this.settings), so the command
                    // still printed "toggled X" and still wrote the file while
                    // changing NOTHING. Silent success, the worst kind of bug.
                    // Fixed: use the confirmed public static SandboxSettings.main
                    // directly (confirmed via IL, same pattern already used for
                    // BuildState.main/MsgDrawer.main elsewhere in this file).
                    //
                    // Finding 3 -- was: no scene gate at all; OnToggle() dereferences
                    // Base.worldBase.paths unchecked, so calling this from the main
                    // menu (no world loaded) threw. Fixed: check Base.worldBase is
                    // non-null first, reported as a distinct reason rather than an
                    // uncaught exception bubbling up as a generic "ERROR '...'" line.
                    //
                    // Finding 4 -- NOT fixed, documented instead: "InfiniteOxygen"
                    // can never work -- there's a UI button for it but no matching
                    // flag or ToggleInfiniteOxygen method on SandboxSettings, so no
                    // reflection call could ever succeed for that name regardless of
                    // how it's resolved. This is a real gap in the GAME's own naming
                    // consistency, not something a probe-side fix can paper over.
                    //
                    // arg is deliberately NOT lowercased the way cmd is (also
                    // flagged in finding 4) -- this is correct behavior, not a bug:
                    // arg becomes part of a real C# method name via reflection
                    // ("Toggle" + arg), and .NET reflection method lookup is
                    // case-sensitive. Lowercasing would make every cheat name fail,
                    // not fewer. The real fix is knowing this: 'cheat InfiniteFuel'
                    // works, 'cheat infinitefuel' will not, and that's expected.
                    if (string.IsNullOrEmpty(arg))
                    {
                        ProbeMod.Result("cheat: FAILED reason=no_arg");
                        break;
                    }

                    object worldBase = Get(FindType("SFS.Base"), "worldBase");
                    if (worldBase == null)
                    {
                        ProbeMod.Result("cheat: FAILED reason=no_world_loaded");
                        break;
                    }

                    object ss = Get(FindType("SFS.World.SandboxSettings"), "main");
                    if (ss == null)
                    {
                        ProbeMod.Result("cheat: FAILED reason=sandboxsettings_main_null");
                        break;
                    }

                    MethodInfo toggleMethod = ss.GetType().GetMethod("Toggle" + arg,
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                    if (toggleMethod == null)
                    {
                        ProbeMod.Result("cheat: FAILED reason=method_not_found method=Toggle" + arg +
                                         " (arg is case-sensitive, must match the real method name exactly)");
                        break;
                    }

                    try { toggleMethod.Invoke(ss, new object[0]); }
                    catch (Exception e)
                    {
                        string msg = e.InnerException != null ? e.InnerException.Message : e.Message;
                        ProbeMod.Result("cheat: FAILED reason=toggle_exception " + msg);
                        break;
                    }

                    ProbeMod.Result("cheat: OK toggled " + arg);
                    break;
                }

                case "describe":
                {
                    // Self-description registry dump (v0.57.0, MCP overhaul
                    // Checkpoint 1). Primary source of truth for command/field
                    // discovery -- see CommandRegistry/FieldRegistry above.
                    string describeJson = RegistryToJson();
                    var describeSb = new StringBuilder(describeJson);
                    Write("sfs_probe_describe.json", describeSb, "self-description registry");
                    ProbeMod.Result("describe: " + CommandRegistry.Length + " commands, " +
                                     FieldRegistry.Length + " fields -> sfs_probe_describe.json");
                    break;
                }

                default:
                    ProbeMod.Result("unknown command: " + cmd);
                    break;
            }
        }

        // ---------- telemetry: inputs (drive a sim) vs truth (check it) ----------

        public static void Sample()
        {
            try
            {
                object r = ActiveRocket();
                if (r == null) return;
                object loc = Unwrap(Get(r, "location"));
                double t = ToD(Get(loc, "time"));

                if (telemetryFields != null)
                {
                    // Scoped mode (v0.29): caller-selected fields only, single
                    // TRUTH file (truth.jsonl), one JSON key per requested field.
                    // See ResolvePath/AppendComputedField below and the
                    // "telemetry" command case above for the spec syntax.
                    //
                    // inputs.jsonl fix (v0.59.0, 2026-09-05): this mode used to
                    // skip inputs.jsonl entirely -- meaning any flight recorded
                    // with a curated field list (which is most physics-validation
                    // flights, since full mode's truth schema is much heavier and
                    // not what those flights want) had NO control-input record at
                    // all, making a real REPLAY-mode forward-integrator run
                    // against it impossible even though the flight itself was
                    // fine. inputs.jsonl recording is now UNCONDITIONAL whenever
                    // Telemetry is on, in both scoped and full mode -- decoupled
                    // from which truth fields were requested, via the exact same
                    // BuildInputsSample() full-mode already uses below, so the two
                    // code paths can never silently drift apart on schema.

                    // Auxiliary conditional triggers (v0.53.0+) -- see the
                    // telemetryTriggers/LoadTelemetryTriggers/CheckTelemetryTriggers
                    // comments (top of this class) and the "telemetry" command
                    // case for the "| <cond>@<sec>:<cmd>; ..." syntax.
                    CheckTelemetryTriggers(r, t);

                    var sb3 = new StringBuilder();
                    // Extracted 2026-09-06 into BuildScopedSample() -- this used
                    // to be an inline loop here (duplicated in telemetrysnapshot's
                    // new scoped-peek mode); factored out so both paths share one
                    // implementation and can't silently drift apart on field
                    // resolution (computed:, partCount, plain dot-paths).
                    sb3.Append(BuildScopedSample(r, t, telemetryFields));

                    // v0.60.0: truth+inputs merged into one live file/line
                    // under the unified telemetry archive lifecycle (single
                    // 'flat'-mode archive, gzip-on-stop) -- see ArchiveOne/
                    // DeletePreviousArchive and the "telemetry" command case.
                    // Same BuildInputsSample() full mode uses, so the two
                    // paths can never silently drift apart on schema.
                    object rbScoped = Get(r, "rb2d");
                    string mergedScoped = MergeJsonObjects(sb3.ToString(), BuildInputsSample(r, rbScoped, t));
                    ProbeMod.Append("sample.jsonl", mergedScoped);

                    sampleCount++;
                    return;
                }

                object rb = Get(r, "rb2d");
                string inputsLine = BuildInputsSample(r, rb, t);
                string truthLine = BuildTruthSample(r, rb, loc, t);
                ProbeMod.Append("sample.jsonl", MergeJsonObjects(truthLine, inputsLine));

                sampleCount++;
            }
            catch (Exception e) { ProbeMod.Log("sample error: " + e.Message); }
        }

        // ---------- JSON rocket-state snapshot recorder (v0.59.0) ----------
        // Independent of Sample()/Telemetry above -- runs on its own
        // 'telemetry json on/off' lifecycle, own file (rocketstate.jsonl), own
        // archive naming, own cadence. Deliberately NOT per-tick: fires at most
        // once per real SECOND OF SIM TIME (gated on Location.time, the same
        // clock truth.jsonl's own "t" uses, so the two files can be correlated
        // on one shared time axis even though they're sampled ~60x apart). A
        // full per-part JSON snapshot at full 60Hz would be ~60x the size for
        // no real analysis benefit -- see the 2026-09-05 chat sizing this
        // against a real 38-part blueprint (~3.3KB/snapshot at 1Hz -> ~2MB for
        // a 10-minute flight, vs. ~120MB at a naive 60Hz).
        //
        // Each entry is a COMPLETE snapshot, not a diff -- a reader never has
        // to reconstruct state by replaying deltas. There is no in-place
        // "current" flag rewritten onto old entries (that would mean
        // rewriting the whole file every second); by convention here, matching
        // every other recorder in this file, the LAST line in rocketstate.jsonl
        // is the current state and every earlier line is history.
        //
        // Per-part id: a part's display name is NOT unique (a rocket with 9
        // fuel tanks has nine parts all named "Fuel Tank"), so name alone
        // can't track one SPECIFIC tank's mass across snapshots. There is no
        // persistent per-part id anywhere in the game's own data (Part has no
        // serialized id/GUID field). This uses .NET object reference identity
        // instead (RuntimeHelpers.GetHashCode) appended to the name -- stable
        // for a given part's entire lifetime in memory, unlike a list index
        // (which shifts for every part after a staging event drops one).
        //
        // "What broke": there is no broken:true flag to read anywhere -- a
        // destroyed part is removed from partHolder.parts entirely, not
        // marked broken in place. A part's id present in snapshot N and
        // absent in snapshot N+1 means it was destroyed or staged off
        // sometime in that ~1s window -- that disappearance IS the signal,
        // recoverable by diffing two consecutive snapshots' part id sets.
        public static void SampleJson()
        {
            try
            {
                object r = ActiveRocket();
                if (r == null) return;
                object loc = Unwrap(Get(r, "location"));
                double t = ToD(Get(loc, "time"));
                if (t - lastJsonSnapshotT < 1.0) return;
                lastJsonSnapshotT = t;

                string line = BuildRocketJsonSnapshot(r, t);
                ProbeMod.Append("rocketstate.jsonl", line);
                jsonSampleCount++;
            }
            catch (Exception e) { ProbeMod.Log("sampleJson error: " + e.Message); }
        }

        static string BuildRocketJsonSnapshot(object r, double t)
        {
            object holder = Get(r, "partHolder");
            object parts = Get(holder, "parts");
            var en = parts as System.Collections.IEnumerable;
            var partLines = new List<string>();
            if (en != null)
            {
                foreach (object part in en)
                {
                    string pname = "?";
                    try { pname = (string)Get(Get(part, "displayName"), "TranslatableName"); } catch { }
                    int refId = System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(part);

                    float mass = float.NaN;
                    try { mass = ToF(GetWrapped2(Get(part, "mass"))); } catch { }

                    // resourcePercent only exists for parts with a ResourceModule
                    // (fuel tanks) -- "null" for everything else, deliberately NOT
                    // 0 (0 would falsely mean "confirmed empty tank").
                    string resourcePctStr = "null";
                    object resOwner = null;
                    object heatOwner = null;
                    foreach (object mv in ModuleValues(part))
                    {
                        string mvType = mv.GetType().Name;
                        if (mvType == "ResourceModule" && resOwner == null) resOwner = mv;
                        else if (mvType == "HeatModule" && heatOwner == null) heatOwner = mv;
                    }
                    if (resOwner != null)
                    {
                        try { resourcePctStr = Num(ToD(GetWrapped2(Get(resOwner, "resourcePercent")))); }
                        catch { }
                    }

                    // Same owner-fallback pattern as GetHeatState above: prefer a
                    // real HeatModule if this part has one, else read Temperature
                    // straight off the part itself.
                    if (heatOwner == null) heatOwner = part;
                    float temp = float.NegativeInfinity;
                    try { temp = ToF(Get(heatOwner, "Temperature")); } catch { }

                    var pb = new StringBuilder();
                    pb.Append("{\"id\":\"").Append(pname.Replace("\"", "'")).Append("#").Append(refId).Append("\"")
                      .Append(",\"name\":\"").Append(pname.Replace("\"", "'")).Append("\"")
                      .Append(",\"mass\":").Append(Num(mass))
                      .Append(",\"resourcePercent\":").Append(resourcePctStr)
                      .Append(",\"temperature\":").Append(NumOrInf(temp))
                      .Append("}");
                    partLines.Add(pb.ToString());
                }
            }

            var sb = new StringBuilder();
            sb.Append("{\"t\":").Append(Num(t));
            sb.Append(",\"partCount\":").Append(partLines.Count);
            sb.Append(",\"mass\":").Append(Num(Get(Get(r, "rb2d"), "mass")));
            sb.Append(",\"parts\":[").Append(string.Join(",", partLines.ToArray())).Append("]");
            sb.Append("}");
            return sb.ToString();
        }

        // Extracted 2026-08-30 from Sample()'s inline body, unchanged logic --
        // now shared between the continuous per-tick recorder (Sample(), which
        // appends the result to inputs.jsonl every FixedUpdate while
        // Telemetry==true) and the new 'telemetrypeek' command (which calls
        // this directly for a ONE-TIME read, independent of whether continuous
        // recording is on, off, or already running -- doesn't touch
        // sampleCount or either file). Keeping this as the single source of
        // truth means peek can never silently drift out of sync with what
        // real recorded telemetry actually contains.
        // Extracted 2026-09-06 from Sample()'s inline scoped-mode loop, so
        // 'telemetrysnapshot <fields>' can reuse the EXACT same field-
        // resolution logic (computed:, partCount, plain dot-paths) as real
        // scoped recording -- one source of truth, can't silently drift.
        // Returns just the field object, e.g. {"t":...,"rb2d.mass":...} --
        // callers merge with BuildInputsSample() themselves if they want the
        // control-input fields too (real scoped recording always does;
        // telemetrysnapshot's scoped mode does not, to keep a one-shot peek
        // fast and minimal -- request rb2d/arrowkeys paths directly instead
        // if control inputs are needed).
        static string BuildScopedSample(object r, double t, string[] fields)
        {
            var sb = new StringBuilder();
            sb.Append("{\"t\":").Append(Num(t));
            foreach (string rawField in fields)
            {
                string f = rawField.Trim();
                if (f.Length == 0) continue;
                if (f.StartsWith("computed:"))
                {
                    string name = f.Substring("computed:".Length);
                    if (!AppendComputedField(name, r, sb))
                        sb.Append(",\"").Append(name).Append("Error\":\"unknown computed field\"");
                }
                else if (f == "partCount")
                {
                    object holderPC = Get(r, "partHolder");
                    object partsPC = Get(holderPC, "parts");
                    var collPC = partsPC as System.Collections.ICollection;
                    sb.Append(",\"partCount\":").Append(collPC != null ? collPC.Count.ToString() : "null");
                }
                else
                {
                    object val = ResolvePath(r, f);
                    sb.Append(",\"").Append(f).Append("\":").Append(Num(val));
                }
            }
            sb.Append("}");
            return sb.ToString();
        }

        static string BuildInputsSample(object r, object rb, double t)
        {
            object throttle = Get(r, "throttle");
            object arrowkeys = Get(r, "arrowkeys");
            float fdt = Time.fixedDeltaTime;
            float thr = ToF(GetWrapped(throttle, "throttlePercent"));
            bool thrOn = ToB(GetWrapped(throttle, "throttleOn"));
            float turnAxis = ToF(GetWrapped(arrowkeys, "turnAxis"));
            float mass = ToF(Get(rb, "mass"));
            float torque = SumEnabledTorque(r);
            bool rcsOn = ToB(GetWrapped(arrowkeys, "rcs"));
            int rcsFiring = CountFiringThrusters(r);
            object eng = GetEngineArray(r);

            // CONFIRMED via IL 2026-08-30 (RcsModule re-verification):
            // DirectionalAxis's real source is Rocket.output_DirectionalAxis
            // (a Vector2_Local), NOT a field on arrowkeys -- needed to
            // reconstruct RcsModule.DirectionThrust's firing decision, which
            // was previously unrecoverable from telemetry.
            object outputDirAxis = GetWrapped2(Get(r, "output_DirectionalAxis"));
            float dirAxisX = ToF(Get(outputDirAxis, "x"));
            float dirAxisY = ToF(Get(outputDirAxis, "y"));

            var si = new StringBuilder();
            si.Append("{\"t\":").Append(Num(t));
            si.Append(",\"fdt\":").Append(fdt.ToString("R"));
            si.Append(",\"m\":").Append(Num(mass));
            si.Append(",\"thr\":").Append(Num(thr));
            si.Append(",\"thrOn\":").Append(thrOn ? "true" : "false");
            si.Append(",\"turnAxis\":").Append(Num(turnAxis));
            si.Append(",\"torque\":").Append(Num(torque));
            si.Append(",\"rcsOn\":").Append(rcsOn ? "true" : "false");
            si.Append(",\"rcsFiring\":").Append(rcsFiring);
            si.Append(",\"directionalAxisX\":").Append(Num(dirAxisX));
            si.Append(",\"directionalAxisY\":").Append(Num(dirAxisY));
            si.Append(",\"engines\":[").Append(string.Join(",", ((List<string>)eng).ToArray())).Append("]");
            si.Append("}");
            return si.ToString();
        }

        // Diagnostic (2026-08-30): calls the REAL AeroModule
        // .GetTemperatureAndShockwave directly -- confirmed public static,
        // takes only a Location -- to get the game's own live air-temperature
        // computation, bypassing the project's own Python reimplementation
        // entirely. Used to definitively separate whether a heat-accumulation
        // gap comes from the temperature FORMULA itself vs. something else in
        // how ApplyHeat integrates it. Returns NaN on any failure so a caller
        // can distinguish "read failed" from "real value is 0" (0 is a normal,
        // common reading -- e.g. outside the atmosphere or not moving).
        static float GetRealAirTemperature(object rocket)
        {
            try
            {
                object loc = Unwrap(Get(rocket, "location"));
                if (loc == null) return float.NaN;
                Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
                if (aeroModuleType == null) return float.NaN;
                MethodInfo getTempMethod = aeroModuleType.GetMethod("GetTemperatureAndShockwave",
                    BindingFlags.Public | BindingFlags.Static);
                if (getTempMethod == null) return float.NaN;
                object[] args = new object[] { loc, 0f, 0f, 0f };
                getTempMethod.Invoke(null, args);
                return ToF(args[3]);
            }
            catch (Exception e)
            {
                ProbeMod.Log("[airtemp] GetTemperatureAndShockwave threw: " + e.Message);
                return float.NaN;
            }
        }

        static string BuildTruthSample(object r, object rb, object loc, double t)
        {
            float mass = ToF(Get(rb, "mass"));
            // world.position/velocity: true double-precision, world-frame,
            // planet-centered vectors -- NOT the same as rb2d's local-frame
            // linearVelocityX/Y used through v0.11.
            object worldPos = GetWrapped(loc, "position");
            object worldVel = GetWrapped(loc, "velocity");

            var st = new StringBuilder();
            st.Append("{\"t\":").Append(Num(t));
            st.Append(",\"h\":").Append(Num(Get(loc, "Height")));
            st.Append(",\"vv\":").Append(Num(Get(loc, "VerticalVelocity")));
            st.Append(",\"m\":").Append(Num(mass));
            st.Append(",\"rot\":").Append(Num(Get(rb, "rotation")));
            st.Append(",\"angv\":").Append(Num(Get(rb, "angularVelocity")));
            st.Append(",\"px\":").Append(Num(Get(worldPos, "x")));
            st.Append(",\"py\":").Append(Num(Get(worldPos, "y")));
            st.Append(",\"vx\":").Append(Num(Get(worldVel, "x")));
            st.Append(",\"vy\":").Append(Num(Get(worldVel, "y")));
            object orbit = GetPredictedOrbit(r);
            st.Append(",\"predApo\":").Append(Num(Get(orbit, "apoapsis")));
            st.Append(",\"predPeri\":").Append(Num(Get(orbit, "periapsis")));
            st.Append(",\"predEcc\":").Append(Num(Get(orbit, "ecc")));
            st.Append(",\"fuelByStage\":").Append(FuelByStage(r));
            var heat = GetHeatState(r);
            st.Append(",\"partCount\":").Append(heat.Item1);
            st.Append(",\"maxTemp\":").Append(Num(heat.Item2));
            float dragArea, dragCopX, dragCopY;
            int dragAllSurfaces, dragExposedSurfaces;
            bool dragOk = TryComputeDragArea(r, out dragArea, out dragCopX, out dragCopY,
                                              out dragAllSurfaces, out dragExposedSurfaces);
            st.Append(",\"dragArea\":").Append(dragOk ? Num(dragArea) : "null");
            st.Append(",\"dragCopX\":").Append(dragOk ? Num(dragCopX) : "null");
            st.Append(",\"dragCopY\":").Append(dragOk ? Num(dragCopY) : "null");
            st.Append(",\"dragSurfaces\":").Append(dragAllSurfaces);
            st.Append(",\"dragExposed\":").Append(dragExposedSurfaces);
            float realAirTemp = GetRealAirTemperature(r);
            st.Append(",\"realAirTemp\":").Append(float.IsNaN(realAirTemp) ? "null" : Num(realAirTemp));
            st.Append(",\"heatParts\":").Append(GetHeatPartsArray(r));
            object planet = Unwrap(Get(loc, "planet"));
            st.Append(",\"body\":\"").Append(Get(planet, "codeName")).Append("\"");
            st.Append("}");
            return st.ToString();
        }

        // FIXED (2026-08-30): old version read Part.temperature -- a plain
        // field that is NEVER written for any part whose surfaces are owned
        // by a HeatModule instead (Part IS a HeatModuleBase, but so is
        // HeatModule, and only one of them is the real owner). That silently
        // under-reported the rocket-wide max on any rocket carrying a
        // HeatModule part.
        //
        // Fixed by reading the abstract Temperature PROPERTY (works on both
        // subclasses via Get()'s field-then-property fallback) off whichever
        // owner is more specific: a part's own HeatModule if it has one,
        // otherwise the Part itself. Best-guess resolution of an open
        // question the docs flag as not fully settled by IL alone, but the
        // more specific tracker is the reasonable default until live data
        // says otherwise.
        //
        // Also fixes the +Inf/-Inf sentinel trap: DissipateHeat writes
        // +Infinity for 'fully cooled, not heated', so a naive max() would
        // treat that sentinel as the hottest part on the rocket. Both +Inf
        // and -Inf are now explicitly excluded before the max comparison.
        static Tuple<int,float> GetHeatState(object rocket)
        {
            try
            {
                object holder = Get(rocket, "partHolder");
                object parts = Get(holder, "parts");
                var en = parts as System.Collections.IEnumerable;
                if (en == null) return Tuple.Create(0, 0f);
                int count = 0;
                float maxTemp = float.NegativeInfinity;
                foreach (object part in en)
                {
                    count++;
                    object owner = null;
                    foreach (object mv in ModuleValues(part))
                    {
                        if (mv.GetType().Name == "HeatModule") { owner = mv; break; }
                    }
                    if (owner == null) owner = part;

                    float temp;
                    try { temp = ToF(Get(owner, "Temperature")); }
                    catch (Exception e)
                    {
                        ProbeMod.Log("[heat-state] Temperature read error on owner " +
                                     Name(owner) + ": " + e.Message);
                        temp = float.NegativeInfinity;
                    }
                    if (!float.IsInfinity(temp) && temp > maxTemp) maxTemp = temp;
                }
                return Tuple.Create(count, float.IsNegativeInfinity(maxTemp) ? 0f : maxTemp);
            }
            catch { return Tuple.Create(0, 0f); }
        }

        // Sums resourcePercent*wetMass per stage using the LIVE stage->part
        // mapping (staging.stages), rather than inferring grouping ourselves.
        static string FuelByStage(object rocket)
        {
            try
            {
                object staging = Get(rocket, "staging");
                object stages = Get(staging, "stages");
                var en = stages as System.Collections.IEnumerable;
                if (en == null) return "null";
                var parts = new List<string>();
                foreach (object stage in en)
                {
                    int id = (int)Get(stage, "stageId");
                    object stageParts = Get(stage, "parts");
                    var pen = stageParts as System.Collections.IEnumerable;
                    double fuel = 0, capacity = 0;
                    if (pen != null)
                    {
                        foreach (object part in pen)
                        {
                            foreach (object mv in ModuleValues(part))
                            {
                                if (mv.GetType().Name != "ResourceModule") continue;
                                double pct = ToD(GetWrapped2(Get(mv, "resourcePercent")));
                                double wet = ToD(GetWrapped2(Get(mv, "wetMass")));
                                fuel += pct * wet;
                                capacity += wet;
                            }
                        }
                    }
                    parts.Add("{\"stage\":" + id + ",\"fuel\":" + Num(fuel) + ",\"capacity\":" + Num(capacity) + "}");
                }
                return "[" + string.Join(",", parts.ToArray()) + "]";
            }
            catch (Exception e) { return "\"error:" + e.Message.Replace("\"", "'") + "\""; }
        }

        // Part.modules dictionary VALUES are stored as single-element ARRAYS
        // keyed by type (e.g. a value of runtime type EngineModule[], not a bare
        // EngineModule), confirmed the hard way once already when reading thrust
        // data by hand. Every helper that walks modules needs this unwrapped, or
        // type-name matching silently finds nothing.
        // Part.modules is keyed by every INTERFACE and BASE CLASS a module
        // implements, not just its concrete type -- so the same physical
        // EngineModule instance appears under multiple keys (EngineModule,
        // HeatModuleBase, ControlModule, INJ_Throttle, ...). Confirmed via
        // diag: one real Hawk engine, six identical entries. Dedupe by
        // reference identity or every module gets double/triple/6x-counted.
        internal static IEnumerable<object> ModuleValues(object part)
        {
            var mf = part.GetType().GetField("modules", BindingFlags.NonPublic | BindingFlags.Instance);
            object modules = mf != null ? mf.GetValue(part) : null;
            var men = modules as System.Collections.IEnumerable;
            if (men == null) yield break;
            var seen = new HashSet<object>(ReferenceEqualityComparer.Instance);
            foreach (object kv in men)
            {
                object mv = Get(kv, "Value");
                if (mv == null) continue;
                if (mv.GetType().IsArray)
                {
                    foreach (object el in (System.Collections.IEnumerable)mv)
                        if (el != null && seen.Add(el)) yield return el;
                }
                else
                {
                    if (seen.Add(mv)) yield return mv;
                }
            }
        }

        // .NET Framework 4.8 has no built-in ReferenceEqualityComparer -- this
        // is the minimal equivalent, since default object equality would work
        // too but being explicit here documents that identity, not value
        // equality, is what dedup needs.
        class ReferenceEqualityComparer : IEqualityComparer<object>
        {
            public static readonly ReferenceEqualityComparer Instance = new ReferenceEqualityComparer();
            public new bool Equals(object a, object b) { return ReferenceEquals(a, b); }
            public int GetHashCode(object o) { return System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(o); }
        }

        // Shared TransformPoint reflection helper (v0.54.0) -- same
        // Vector2->Vector3->TransformPoint->Vector2 pattern already used
        // inline in "rcsforce" (explicit-overload resolution, since
        // UnityEngine.CoreModule commonly has multiple TransformPoint/
        // Vector2<->Vector3 overloads that throw AmbiguousMatchException on
        // a plain GetMethod(name) lookup). Extracted here so
        // "getforwardstartinfo" doesn't duplicate it a second time; the
        // rcsforce inline copy is left as-is (additive change, not a
        // refactor of working code). Cache the three ref params ACROSS
        // calls within one command (the Vector2 type doesn't change
        // between parts), not just once per part.
        static bool TryTransformPointToWorld(object transform, object localPointVec2,
            ref Type vector3TypeCache, ref MethodInfo vec2ToVec3Method, ref MethodInfo transformPointMethod,
            out float worldX, out float worldY)
        {
            worldX = float.NaN; worldY = float.NaN;
            if (transform == null || localPointVec2 == null) return false;
            if (vec2ToVec3Method == null)
            {
                Type vector2TypeLocal = localPointVec2.GetType();
                vec2ToVec3Method = vector2TypeLocal.GetMethod("op_Implicit",
                    BindingFlags.Public | BindingFlags.Static, null, new Type[] { vector2TypeLocal }, null);
                if (vec2ToVec3Method == null) return false;
                vector3TypeCache = vec2ToVec3Method.ReturnType;
                transformPointMethod = transform.GetType().GetMethod("TransformPoint",
                    BindingFlags.Public | BindingFlags.Instance, null, new Type[] { vector3TypeCache }, null);
            }
            if (transformPointMethod == null) return false;
            object vec3 = vec2ToVec3Method.Invoke(null, new object[] { localPointVec2 });
            object worldVec3 = transformPointMethod.Invoke(transform, new object[] { vec3 });
            worldX = ToF(Get(worldVec3, "x"));
            worldY = ToF(Get(worldVec3, "y"));
            return true;
        }

        // Rotates a WORLD-frame CoM-relative offset into the BODY-LOCAL
        // frame forward_sim.py's craft_config expects ("position_local",
        // re-rotated by theta each future timestep via its own
        // _rotate_body_vector). This is the INVERSE of that function's
        // rotation (confirmed CCW-positive, matching Unity's
        // Rigidbody2D.rotation convention) -- passing -rocketRotationDeg
        // undoes the craft's CURRENT orientation so what's stored is a
        // pure body-fixed offset, independent of theta at capture time.
        static void WorldOffsetToBodyLocal(float worldOffX, float worldOffY, float rocketRotationDeg,
            out float localX, out float localY)
        {
            double rad = -rocketRotationDeg * Math.PI / 180.0;
            double c = Math.Cos(rad), s = Math.Sin(rad);
            localX = (float)(worldOffX * c - worldOffY * s);
            localY = (float)(worldOffX * s + worldOffY * c);
        }

        // Constructs a genuine Vector2-TYPED object at runtime, matching
        // whatever exact loaded type an ALREADY-OBTAINED Vector2 instance
        // has (e.g. Rigidbody2D.worldCenterOfMass) -- same pattern rcsforce
        // already uses for posToComVec2, needed because a Composed_Vector2's
        // unwrapped x/y are plain floats, not a Vector2, but
        // TryTransformPointToWorld needs a real Vector2-shaped object to
        // feed its op_Implicit->Vector3 conversion.
        static object MakeVector2Like(object templateVec2, float x, float y)
        {
            object v = Activator.CreateInstance(templateVec2.GetType());
            templateVec2.GetType().GetField("x").SetValue(v, x);
            templateVec2.GetType().GetField("y").SetValue(v, y);
            return v;
        }

        // Returns ONE ENTRY PER ENGINE/BOOSTER MODULE FOUND (regardless of
        // on/off state -- the state itself is data, not a filter). Replaces
        // the old GetEngineDirection(), which returned only the FIRST ACTIVE
        // engine as a single tuple. That was wrong on two counts, both
        // flagged in high_level_checklist.md: (1) there is no thrust
        // summation anywhere in the game -- each engine calls
        // AddForceAtPosition independently, so one engine's direction was
        // never a meaningful summary of a multi-engine rocket; (2) it missed
        // BoosterModule entirely, which uses thrustVector/boosterPrimed
        // rather than thrustNormal/engineOn.
        //
        // Also fixes the silent-failure half of the same checklist item: the
        // old function ended in a bare `catch { }`, so of its three candidate
        // explanations for "why do thrustDirX/Y/gimbalOn/throttleOut never
        // populate" (no matching module / engineOn false outside a burn /
        // an exception thrown and swallowed), the third was unfalsifiable by
        // inspection alone. Every read below is now individually try/caught
        // and LOGGED (not swallowed) with the specific part name, so a real
        // flight settles which of the three it actually was.
        static List<string> GetEngineArray(object rocket)
        {
            var results = new List<string>();
            object holder = Get(rocket, "partHolder");
            object parts = Get(holder, "parts");
            var en = parts as System.Collections.IEnumerable;
            if (en == null) return results;
            foreach (object part in en)
            {
                string pname = "?";
                try { pname = (string)Get(Get(part, "displayName"), "TranslatableName"); } catch { }
                foreach (object mv in ModuleValues(part))
                {
                    string typeName = mv.GetType().Name;
                    if (typeName == "EngineModule")
                    {
                        try
                        {
                            bool engineOn = ToB(GetWrapped2(Get(mv, "engineOn")));
                            object normal = Get(mv, "thrustNormal");
                            float dx = ToF(GetWrapped2(Get(normal, "x")));
                            float dy = ToF(GetWrapped2(Get(normal, "y")));
                            bool gimbal = ToB(GetWrapped2(Get(mv, "gimbalOn")));
                            float throttleOut = ToF(GetWrapped2(Get(mv, "throttle_Out")));
                            var esb = new StringBuilder();
                            esb.Append("{\"part\":").Append(Q(pname));
                            esb.Append(",\"type\":\"engine\"");
                            esb.Append(",\"engineOn\":").Append(engineOn ? "true" : "false");
                            esb.Append(",\"thrustDirX\":").Append(Num(dx));
                            esb.Append(",\"thrustDirY\":").Append(Num(dy));
                            esb.Append(",\"gimbalOn\":").Append(gimbal ? "true" : "false");
                            esb.Append(",\"throttleOut\":").Append(Num(throttleOut));
                            esb.Append("}");
                            results.Add(esb.ToString());
                        }
                        catch (Exception e)
                        {
                            ProbeMod.Log("[engine-array] EngineModule read error on part \"" + pname + "\": " + e.Message);
                            results.Add("{\"part\":" + Q(pname) + ",\"type\":\"engine\",\"error\":" + Q(e.Message) + "}");
                        }
                    }
                    else if (typeName == "BoosterModule")
                    {
                        try
                        {
                            bool primed = ToB(GetWrapped2(Get(mv, "boosterPrimed")));
                            object vec = Get(mv, "thrustVector");
                            float vx = ToF(GetWrapped2(Get(vec, "x")));
                            float vy = ToF(GetWrapped2(Get(vec, "y")));
                            var bsb = new StringBuilder();
                            bsb.Append("{\"part\":").Append(Q(pname));
                            bsb.Append(",\"type\":\"booster\"");
                            bsb.Append(",\"boosterPrimed\":").Append(primed ? "true" : "false");
                            bsb.Append(",\"thrustVectorX\":").Append(Num(vx));
                            bsb.Append(",\"thrustVectorY\":").Append(Num(vy));
                            bsb.Append("}");
                            results.Add(bsb.ToString());
                        }
                        catch (Exception e)
                        {
                            ProbeMod.Log("[engine-array] BoosterModule read error on part \"" + pname + "\": " + e.Message);
                            results.Add("{\"part\":" + Q(pname) + ",\"type\":\"booster\",\"error\":" + Q(e.Message) + "}");
                        }
                    }
                }
            }
            return results;
        }

        // RCS applies force per-thruster with its own on/off selection logic
        // (TorqueThrust/DirectionThrust threshold checks in RcsModule.FixedUpdate)
        // that we do not replicate. This only counts how many thrusters are
        // CURRENTLY firing, so RCS-affected ticks can be flagged and excluded
        // from rotation-model validation rather than silently mispredicted.
        static int CountFiringThrusters(object rocket)
        {
            try
            {
                object holder = Get(rocket, "partHolder");
                object parts = Get(holder, "parts");
                var en = parts as System.Collections.IEnumerable;
                if (en == null) return 0;
                int firing = 0;
                foreach (object part in en)
                {
                    foreach (object mv in ModuleValues(part))
                    {
                        if (mv.GetType().Name != "RcsModule") continue;
                        object thrusters = Get(mv, "thrusters");
                        var ten = thrusters as System.Collections.IEnumerable;
                        if (ten == null) continue;
                        foreach (object th in ten)
                        {
                            object effect = Get(th, "effect");
                            object targetTime = Get(effect, "targetTime");
                            float v = ToF(GetWrapped2(targetTime));
                            if (v > 0.5f) firing++;   // set to 1.0 when a thruster is actively firing
                        }
                    }
                }
                return firing;
            }
            catch { return 0; }
        }

        static float SumEnabledTorque(object rocket)
        {
            try
            {
                object holder = Get(rocket, "partHolder");
                object parts = Get(holder, "parts");
                var en = parts as System.Collections.IEnumerable;
                if (en == null) return 0f;
                float total = 0f;
                foreach (object part in en)
                {
                    foreach (object mv in ModuleValues(part))
                    {
                        if (mv.GetType().Name != "TorqueModule") continue;
                        bool isEnabled = ToB(GetWrapped2(Get(mv, "enabled")));
                        if (!isEnabled) continue;
                        total += ToF(GetWrapped2(Get(mv, "torque")));
                    }
                }
                return total;
            }
            catch { return 0f; }
        }

        // Physics.trajectory is a raw field that's only current when the rocket
        // is on rails (timewarp). Under live physics -- our situation for the
        // whole test -- the actual up-to-date prediction lives in a separately
        // cached field, populated only by CALLING Physics.GetTrajectory(), which
        // is what the game's own UI calls to show the map-view apoapsis. Reading
        // the raw field directly (as earlier versions did) returns stale/empty
        // data during any live-physics flight -- confirmed by predApo showing
        // null all through this flight while the in-game readout showed 370.2km.
        static object GetPredictedOrbit(object rocket)
        {
            try
            {
                object physics = Get(rocket, "physics");
                object trajectory = InvokeReturn(physics, "GetTrajectory", new object[0]);
                object paths = Get(trajectory, "paths");
                var en = paths as System.Collections.IEnumerable;
                if (en == null) return null;
                foreach (object p in en)
                    if (p != null && p.GetType().Name == "Orbit") return p;
            }
            catch { }
            return null;
        }

        // ---------- numeric coercion ----------

        static string Num(object o)
        {
            if (o == null) return "null";
            try { return Convert.ToDouble(o).ToString("R", CultureInfo.InvariantCulture); }
            catch { return "null"; }
        }
        static double ToD(object o) { try { return Convert.ToDouble(o); } catch { return 0; } }
        static float ToF(object o) { try { return Convert.ToSingle(o); } catch { return 0f; } }
        internal static bool ToB(object o) { return (o is bool) && (bool)o; }

        static object GetWrapped(object owner, string member) { return GetWrapped2(Get(owner, member)); }
        static object GetWrapped2(object w)
        {
            if (w == null) return null;
            // FIXED (2026-08-30): root-caused the long-standing
            // AmbiguousMatchException on EngineModule reads (previously seen
            // once, deep in a 73k-sample flight; now trivially reproducible on
            // ANY engine, first tick, right on the pad). Root cause: some
            // wrapper types HIDE (via `new`, not `override`) a base class's
            // same-named "Value" property with a DIFFERENT return type --
            // confirmed for Float_Reference : Double_Reference, which
            // redeclares its own float Value hiding ReferenceVariable<double>
            // .Value (see docs/sfs_reference/00-infrastructure/
            // variables-wrapper-family.md). The old plain
            // t.GetProperty("Value", flags) walks the WHOLE type hierarchy and
            // throws AmbiguousMatchException the instant it finds two
            // same-named properties that aren't a normal override pair --
            // throttle_Out is a Float_Reference, so this fired on every
            // single engine read, every tick, silently aborting the entire
            // per-engine block (the whole thing lives in one try/catch).
            //
            // Fixed by walking from the most-derived runtime type UPWARD,
            // taking the first DECLARED-ONLY "Value" property found at each
            // level. DeclaredOnly can never be ambiguous (a single type can't
            // declare the same property signature twice), and the
            // most-derived declaration is exactly what a real `.Value` call
            // site binds to anyway -- this isn't a workaround, it's the
            // correct resolution.
            for (Type cur = w.GetType(); cur != null; cur = cur.BaseType)
            {
                var pDeclared = cur.GetProperty("Value", BindingFlags.Public | BindingFlags.NonPublic |
                                                 BindingFlags.Instance | BindingFlags.DeclaredOnly);
                if (pDeclared != null)
                {
                    try { return pDeclared.GetValue(w, null); }
                    catch (Exception e)
                    {
                        ProbeMod.Log("[GetWrapped2] declared Value getter threw on " +
                                     cur.FullName + ": " + e.Message);
                        return null;
                    }
                }
            }
            var f = w.GetType().GetField("value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (f != null) { try { return f.GetValue(w); } catch { } }
            return w;
        }

        // ---------- archiving (v0.60.0: unified lifecycle, both modes) ----------
        // One naming scheme for both flat and parts modes:
        // telemetry_<mode>_<timestamp>.jsonl -> gzipped to .jsonl.gz on
        // ArchiveOne, raw deleted immediately after. At most one archived
        // .gz per mode ever sits on disk -- DeletePreviousArchive(mode) is
        // called at the START of the NEXT recording of that mode (not here),
        // so an untagged flight's .gz survives until superseded, giving a
        // window to tag it. sfsprobe_tag_flight copies a .gz into
        // archive/kept/ to make it permanent -- that's the only path out of
        // this overwrite policy.

        // Deletes a stray leftover LIVE file (uncommitted, from an uncleanly-
        // stopped previous recording) before a fresh one starts. Not archived
        // -- partial data from a botched run isn't worth preserving over the
        // last COMPLETED run's archive, which DeletePreviousArchive handles
        // separately.
        static void ClearLiveFile(string liveName)
        {
            try
            {
                string live = Path.Combine(ProbeMod.OutDir ?? ".", liveName);
                if (File.Exists(live)) File.Delete(live);
            }
            catch (Exception e) { ProbeMod.Log("ClearLiveFile(" + liveName + ") failed: " + e.Message); }
        }

        // Deletes any previously archived .gz for this mode ("flat" or
        // "parts") before a new recording of that mode starts. This is what
        // makes "new runs overwrite previous results" real -- called from
        // StartRecording/StartJsonRecording, not from ArchiveOne itself, so
        // the just-completed archive survives until the NEXT run begins
        // (giving sfsprobe_tag_flight a window to promote it into
        // archive/kept/ first if it's worth keeping).
        static void DeletePreviousArchive(string mode)
        {
            try
            {
                string archiveDir = Path.Combine(ProbeMod.OutDir ?? ".", "archive");
                if (!Directory.Exists(archiveDir)) return;
                foreach (string f in Directory.GetFiles(archiveDir, "telemetry_" + mode + "_*.jsonl.gz"))
                {
                    try { File.Delete(f); ProbeMod.Log("deleted previous archive: " + Path.GetFileName(f)); }
                    catch (Exception e) { ProbeMod.Log("could not delete previous archive " + f + ": " + e.Message); }
                }
            }
            catch (Exception e) { ProbeMod.Log("DeletePreviousArchive(" + mode + ") failed: " + e.Message); }
        }

        // Moves the live file into archive/ under the unified naming scheme,
        // gzips it, then deletes the raw .jsonl -- the raw form only ever
        // exists ON DISK during the recording itself, per the project's
        // storage rule of thumb (2026-09-05): JSON only lives during the
        // run; once stopped, it's zipped; new runs overwrite previous
        // results (see DeletePreviousArchive, called separately at the
        // START of the next recording, not here).
        static string ArchiveOne(string liveName, string mode)
        {
            try
            {
                string live = Path.Combine(ProbeMod.OutDir ?? ".", liveName);
                if (!File.Exists(live)) return null;
                if (new FileInfo(live).Length == 0) { File.Delete(live); return null; }

                string archiveDir = Path.Combine(ProbeMod.OutDir ?? ".", "archive");
                Directory.CreateDirectory(archiveDir);
                string stamp = DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss");
                string name = "telemetry_" + mode + "_" + stamp + ".jsonl";
                string dest = Path.Combine(archiveDir, name);
                File.Move(live, dest);

                string gzName = name + ".gz";
                string gzDest = Path.Combine(archiveDir, gzName);
                using (FileStream rawStream = File.OpenRead(dest))
                using (FileStream gzStream = File.Create(gzDest))
                using (GZipStream gzip = new GZipStream(gzStream, CompressionMode.Compress))
                {
                    rawStream.CopyTo(gzip);
                }
                File.Delete(dest);   // raw only lives during the run -- see rule of thumb above

                ProbeMod.Log("archived -> archive/" + gzName);
                return "archive/" + gzName;
            }
            catch (Exception e) { ProbeMod.Log("archive failed (" + liveName + "): " + e.Message); return null; }
        }

        // Merges two flat, single-line JSON objects of the form {"t":X,...}
        // into one -- used to fold BuildInputsSample's output into the same
        // per-tick record as BuildTruthSample's/scoped mode's, now that both
        // write to one live file under the unified archive lifecycle
        // (v0.60.0). Relies on the invariant (true for every caller) that
        // both strings are flat objects ending in a bare "}" with nothing
        // after it. b's leading {"t":<num> is redundant (same tick, same
        // value as a's) and is stripped up to and including the first comma.
        static string MergeJsonObjects(string a, string b)
        {
            int firstComma = b.IndexOf(',');
            string bRemainder = firstComma >= 0 ? b.Substring(firstComma) : "";
            return a.Substring(0, a.Length - 1) + bRemainder;
        }

        // ---------- dumps (menu/world/flight snapshots, unchanged) ----------

        public static void DumpMenu(string why)
        {
            object parts = Get(FindComponent("SFS.Parts.PartsLoader"), "parts");
            if (parts == null) { ProbeMod.Log(why + ": no parts"); return; }
            var sb = Header();
            sb.Append("  \"careerState\": ").Append(Dump(Get(FindComponent("SFS.Career.CareerState"), "state"), 1)).Append(",\n");
            sb.Append("  \"parts\": ").Append(DumpPartsWithGeometry(parts, false)).Append("\n}\n");
            Write("sfs_probe_menu.json", sb, why + " parts=" + Describe(parts));
        }

        // Same per-part walk as DumpCollection, but appends explicit drag-surface
        // geometry that the generic depth-limited Dump() cannot reach: SurfaceData
        // .surfacesFast -> List<Surfaces> -> Surfaces.points is FOUR levels deep
        // from a Part (Part -> SurfaceData -> List<Surfaces> -> Surfaces ->
        // points[]), past Dump()'s depth-3 cutoff, so it prints as just the type
        // name "Vector2[]" with no actual numbers unless pulled out explicitly
        // like this -- confirmed by tracing the depth count before writing this.
        // This is local-space outline geometry (fixed per part, independent of
        // being placed on a rocket), the last missing input for computing
        // dragArea ourselves via SFS's own GetDragSurfaces/CalculateDragForce
        // algorithm rather than fitting it empirically per vehicle shape.
        static string DumpPartsWithGeometry(object parts, bool forceInit)
        {
            var en = parts as System.Collections.IEnumerable;
            if (en == null) return DumpCollection(parts);
            var items = new List<string>();
            foreach (object item in en)
            {
                object part = item;
                var it = part == null ? null : part.GetType();
                if (it != null && it.IsGenericType && it.GetGenericTypeDefinition() == typeof(KeyValuePair<,>))
                    part = Get(part, "Value");
                if (part == null) continue;
                string baseDump = Dump(part, 0);
                string geom = DumpPartGeometry(part, forceInit);
                // splice "surfaceGeometry": [...] into the object just before its closing brace
                if (baseDump.EndsWith("}") && geom != null)
                    baseDump = baseDump.Substring(0, baseDump.Length - 1) + ", \"surfaceGeometry\": " + geom + "}";
                items.Add(baseDump);
            }
            return "[\n    " + string.Join(",\n    ", items.ToArray()) + "\n  ]";
        }

        // Extracts a part's REAL parametric variable definitions -- name and
        // value for every entry in doubleVariables/boolVariables/
        // stringVariables.saves -- past the generic Dump()'s depth-3 cutoff,
        // which only shows the bare type name "VariableSave" for these, not
        // their actual contents (confirmed empirically on "Fuel Tank": 7
        // doubleVariables entries all rendered as just the string
        // "VariableSave", 2026-08-29). Field names on VariableSave-like
        // objects are read GENERICALLY (whatever public fields exist) since
        // the exact schema was never independently confirmed via IL before
        // this was written -- safer than guessing specific field names and
        // silently getting nothing back. If a group's "saves" doesn't
        // enumerate cleanly (boolVariables showed a different shape than
        // doubleVariables/stringVariables in one early manual dump -- {
        // "Capacity":0,"Count":0} rather than a real array, suggesting a
        // different underlying container), falls back to a plain deeper
        // Dump() of the raw group so nothing is silently lost either way.
        static string DumpVariablesModule(object part)
        {
            try
            {
                object vm = Get(part, "variablesModule");
                if (vm == null) return "null";
                var groups = new List<string>();
                foreach (string groupName in new string[] { "doubleVariables", "boolVariables", "stringVariables" })
                {
                    string groupJson;
                    try
                    {
                        object group = Get(vm, groupName);
                        object saves = Get(group, "saves");
                        var entries = new List<string>();
                        var senum = saves as System.Collections.IEnumerable;
                        if (senum != null)
                        {
                            foreach (object save in senum)
                            {
                                if (save == null) continue;
                                entries.Add(DumpObjectFieldsGeneric(save));
                            }
                        }
                        groupJson = entries.Count > 0
                            ? "[" + string.Join(",", entries.ToArray()) + "]"
                            : Dump(saves, 1);   // fallback: whatever the raw shape actually is
                    }
                    catch (Exception e) { groupJson = "\"error:" + e.Message.Replace("\"", "'") + "\""; }
                    groups.Add("\"" + groupName + "\":" + groupJson);
                }
                return "{" + string.Join(",", groups.ToArray()) + "}";
            }
            catch (Exception e) { return "\"error:" + e.Message.Replace("\"", "'") + "\""; }
        }

        // Extracts a part's REAL magnet/attachment points -- the actual data
        // behind SFS's snap system (SFS.Builds.HoldGrid + MagnetModule,
        // confirmed via IL 2026-08-29). This is NOT a fixed coordinate grid;
        // parts snap to each other via real geometric attachment points
        // (MagnetModule.points, each a local-space Composed_Vector2 position),
        // matched through MagnetModule.GetAllSnapOffsets -- the same method
        // the game's own interactive placement UI calls. Direct blueprint
        // injection (loadblueprintbuild/loadblueprint) bypasses that snap
        // step entirely, which is why hand-picked positions can land a part
        // somewhere a human dragging with the mouse never could.
        //
        // Point.position is a simple field, not mesh geometry -- unlike
        // surfaceGeometry (gated behind Part.InitializePart(), unsafe on bare
        // catalog prefabs), this is hypothesized to be safely readable
        // straight from the catalog. Not yet confirmed live as of first
        // write -- if empty/wrong on catalog parts, magnet data will need
        // to come from already-placed instances instead, same as geometry.
        static string DumpMagnetPoints(object part)
        {
            try
            {
                object magnet = null;
                foreach (object mv in ModuleValues(part))
                {
                    if (mv.GetType().Name == "MagnetModule") { magnet = mv; break; }
                }
                if (magnet == null) return "null";
                object pointsArr = Get(magnet, "points");
                var pen = pointsArr as System.Collections.IEnumerable;
                if (pen == null) return "[]";
                var items = new List<string>();
                foreach (object pt in pen)
                {
                    if (pt == null) continue;
                    object posObj = Get(pt, "position");
                    float px = ToF(GetWrapped2(Get(posObj, "x")));
                    float py = ToF(GetWrapped2(Get(posObj, "y")));
                    bool occupied = ToB(Get(pt, "occupied"));
                    items.Add("{\"x\":" + Num(px) + ",\"y\":" + Num(py) + ",\"occupied\":" + (occupied ? "true" : "false") + "}");
                }
                return "[" + string.Join(",", items.ToArray()) + "]";
            }
            catch (Exception e) { return "\"error:" + e.Message.Replace("\"", "'") + "\""; }
        }

        // Generic, name-agnostic public-field dump for ANY object -- used
        // wherever the exact schema wasn't independently confirmed via IL
        // before this was written (VariableSave for parametric variables,
        // VariantRef for part variants), so field names are read whatever
        // they actually are rather than guessed and silently missed.
        //
        // Reads BOTH fields (public AND non-public -- Unity code commonly
        // uses [SerializeField] private, same reasoning the main Get()
        // helper elsewhere in this file already applies) AND public
        // properties with a "simple" return type (matching the main Dump()
        // function's own property walk). Checking fields-only was a real
        // gap -- if the meaningful data on an object like VariantRef lives
        // behind a private field or a property instead of a public field,
        // the fields-only version would have come back looking empty
        // (falling through to just the bare type name) even though real
        // data was sitting right there.
        static string DumpObjectFieldsGeneric(object o)
        {
            try
            {
                var parts = new List<string>();
                foreach (var f in o.GetType().GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance))
                {
                    if (typeof(Delegate).IsAssignableFrom(f.FieldType)) continue;
                    object v;
                    try { v = f.GetValue(o); } catch { continue; }
                    parts.Add(Q(f.Name) + ":" + Dump(v, 2));
                }
                foreach (var p in o.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
                {
                    if (p.GetIndexParameters().Length > 0) continue;
                    if (!IsSimple(p.PropertyType)) continue;
                    object v;
                    try { v = p.GetValue(o, null); } catch { continue; }
                    parts.Add(Q(p.Name) + ":" + Dump(v, 2));
                }
                if (parts.Count == 0) return Q(o.GetType().Name);
                return "{" + string.Join(",", parts.ToArray()) + "}";
            }
            catch (Exception e) { return "\"error:" + e.Message.Replace("\"", "'") + "\""; }
        }

        static string DumpPartGeometry(object part, bool forceInit)
        {
            try
            {
                // surfacesFast is NOT populated at load -- it's a side effect of
                // the part's procedural mesh generation (BoxPolygon/CustomPolygon/
                // CustomSurfaces .Output() -> SurfaceData.SetData()), which only
                // runs from Part.InitializePart(). Confirmed via IL: SetData has
                // exactly one writer path, gated behind that call chain.
                //
                // Calling InitializePart() on a bare, never-instantiated PREFAB
                // (PartsLoader.parts catalog entries, no full GameObject/Transform
                // context) appears to HANG the game -- confirmed the hard way.
                // forceInit is therefore OFF by default and only used where the
                // part is a real, placed instance on an actual rocket.
                if (forceInit) InvokeReturn(part, "InitializePart", new object[0]);

                foreach (object mv in ModuleValues(part))
                {
                    if (mv.GetType().Name != "SurfaceData") continue;
                    object fast = Get(mv, "surfacesFast");
                    var sen = fast as System.Collections.IEnumerable;
                    if (sen == null) return "[]";
                    var surfaces = new List<string>();
                    foreach (object surf in sen)
                    {
                        object pts = Get(surf, "points");
                        bool loop = ToB(Get(surf, "loop"));
                        var pen = pts as System.Collections.IEnumerable;
                        var ptStrs = new List<string>();
                        if (pen != null)
                            foreach (object p in pen)
                            {
                                if (p is Vector2) { var v2 = (Vector2)p; ptStrs.Add("[" + v2.x.ToString("R") + "," + v2.y.ToString("R") + "]"); }
                            }
                        surfaces.Add("{\"points\":[" + string.Join(",", ptStrs.ToArray()) + "],\"loop\":" + (loop ? "true" : "false") + "}");
                    }
                    return "[" + string.Join(",", surfaces.ToArray()) + "]";
                }
            }
            catch (Exception e) { return "\"error:" + e.Message.Replace("\"", "'") + "\""; }
            return "[]";   // no SurfaceData module on this part (e.g. non-physical parts)
        }

        public static void DumpWorld(string why)
        {
            object pl = FindComponent("SFS.WorldBase.PlanetLoader");
            object planets = Get(pl, "planets");
            var c = planets as System.Collections.ICollection;
            if (planets == null || c == null || c.Count == 0) return;
            var sb = Header();
            sb.Append("  \"planets\": ").Append(DumpCollection(planets)).Append("\n}\n");
            Write("sfs_probe_world.json", sb, why + " planets=" + Describe(planets));
            WroteWorld = true;
        }

        public static void DumpFlight(string why)
        {
            object gm = FindComponent("SFS.World.GameManager");
            var list = Get(gm, "rockets") as System.Collections.IEnumerable;
            if (list == null)
            {
                object one = ActiveRocket();
                if (one == null) { ProbeMod.Result(why + ": no rockets"); return; }
                list = new object[] { one };
            }
            var sb = Header();
            sb.Append("  \"aeroData\": ").Append(Dump(Get(gm, "aeroData"), 2)).Append(",\n");
            sb.Append("  \"rockets\": [\n");
            int nr = 0, np = 0; bool first = true;
            foreach (object r0 in list)
            {
                object r = Unwrap(r0);
                if (r == null) continue;
                nr++;
                if (!first) sb.Append(",\n");
                first = false;
                sb.Append("    {\n      \"type\": ").Append(Q(r.GetType().FullName)).Append(",\n");
                foreach (string m in new string[] { "mass", "aero", "physics", "resources", "throttle", "location", "rb2d" })
                    sb.Append("      ").Append(Q(m)).Append(": ").Append(Dump(Unwrap(Get(r, m)), 2)).Append(",\n");
                object parts = Get(Get(r, "partHolder"), "parts");
                var pc = parts as System.Collections.ICollection;
                if (pc != null) np += pc.Count;
                sb.Append("      \"parts\": ").Append(DumpPartsWithGeometry(parts, true)).Append("\n    }");
            }
            sb.Append("\n  ]\n}\n");
            Write("sfs_probe_flight.json", sb, why + " rockets=" + nr + " parts=" + np);
            ProbeMod.Result("snapshot rockets=" + nr + " parts=" + np);
        }

        // ---------- helpers ----------

        static int RocketCount()
        {
            var c = Get(FindComponent("SFS.World.GameManager"), "rockets") as System.Collections.ICollection;
            return c == null ? -1 : c.Count;
        }

        static object ActiveRocket()
        {
            object r = Unwrap(Get(FindComponent("SFS.World.PlayerController"), "player"));
            if (r != null && r.GetType().Name.Contains("Rocket")) return r;
            var list = Get(FindComponent("SFS.World.GameManager"), "rockets") as System.Collections.IEnumerable;
            if (list != null) foreach (object o in list) { object u = Unwrap(o); if (u != null) return u; }
            return null;
        }

        static string Name(object o) { return o == null ? "null" : o.GetType().FullName; }

        static object Unwrap(object o)
        {
            for (int i = 0; i < 6 && o != null; i++)
            {
                Type t = o.GetType();
                if (t.Name.Contains("Rocket") || t.Name == "Location" || t.Name == "Planet") return o;
                var p = t.GetProperty("Value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                var f = t.GetField("value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                object next = null;
                if (p != null) { try { next = p.GetValue(o, null); } catch { } }
                if (next == null && f != null) { try { next = f.GetValue(o); } catch { } }
                if (next == null || ReferenceEquals(next, o)) return o;
                o = next;
            }
            return o;
        }

        static bool SetWrapped(object owner, string member, object val)
        {
            object w = Get(owner, member);
            if (w == null) return false;
            // Same DeclaredOnly-walk fix as GetWrapped2 above, applied to the
            // write side for consistency -- hasn't been observed to throw yet
            // (no current command writes to a Float_Reference-typed field),
            // but it's the identical latent AmbiguousMatchException risk, so
            // fixed preemptively rather than waiting for a second silent
            // failure to surface it.
            for (Type cur = w.GetType(); cur != null; cur = cur.BaseType)
            {
                var pDeclared = cur.GetProperty("Value", BindingFlags.Public | BindingFlags.NonPublic |
                                                 BindingFlags.Instance | BindingFlags.DeclaredOnly);
                if (pDeclared != null && pDeclared.CanWrite)
                {
                    try { pDeclared.SetValue(w, Convert.ChangeType(val, pDeclared.PropertyType), null); return true; }
                    catch (Exception e)
                    {
                        ProbeMod.Log("[SetWrapped] declared Value setter threw on " +
                                     cur.FullName + ": " + e.Message);
                        return false;
                    }
                }
            }
            var f = w.GetType().GetField("value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (f != null)
            {
                try { f.SetValue(w, Convert.ChangeType(val, f.FieldType)); return true; } catch { }
            }
            return false;
        }

        static void Invoke(object o, string method, object[] args)
        {
            if (o == null) throw new Exception("target null for " + method);
            Type t = o as Type ?? o.GetType();
            object target = (o is Type) ? null : o;
            var m = t.GetMethod(method, BindingFlags.Public | BindingFlags.NonPublic |
                    (target == null ? BindingFlags.Static : BindingFlags.Instance));
            if (m == null) throw new Exception("no method " + method + " on " + t.Name);
            m.Invoke(target, args);
        }

        static object InvokeReturn(object o, string method, object[] args)
        {
            if (o == null) return null;
            Type t = o as Type ?? o.GetType();
            object target = (o is Type) ? null : o;
            var m = t.GetMethod(method, BindingFlags.Public | BindingFlags.NonPublic |
                    (target == null ? BindingFlags.Static : BindingFlags.Instance));
            if (m == null) return null;
            try { return m.Invoke(target, args); } catch { return null; }
        }

        // Explicit-overload-safe STATIC invoke -- needed because some classes
        // in this codebase (e.g. Aero_Rocket.GetDragSurfaces) have two static/
        // instance overloads sharing the same name; plain GetMethod(name, flags)
        // throws AmbiguousMatchException in that case. Callers pass the exact
        // parameter types to disambiguate.
        static object InvokeStatic(Type t, string method, Type[] paramTypes, object[] args)
        {
            try
            {
                MethodInfo m = t.GetMethod(method,
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static,
                    null, paramTypes, null);
                if (m == null) return null;
                return m.Invoke(null, args);
            }
            catch (Exception e)
            {
                ProbeMod.Log("InvokeStatic " + method + " failed: " +
                    (e.InnerException != null ? e.InnerException.Message : e.Message));
                return null;
            }
        }

        // Shared drag computation (v0.28) -- same confirmed call chain as the
        // 'dragarea' command case above (Aero_Rocket.GetDragSurfaces ->
        // AeroModule.GetExposedSurfaces -> AeroModule.CalculateDragForce, real
        // velocity-derived rotation, not identity), minus the sample-segment
        // diagnostic dump. Reused per-tick by Sample() so every truth.jsonl row
        // carries a real, live dragArea reading instead of needing a separate
        // manual 'dragarea' command each time. Returns false (all-zero outs) on
        // any resolution/invocation failure so a caller can write null rather
        // than a misleading zero.
        static bool TryComputeDragArea(object rocket, out float drag, out float copX, out float copY,
                                        out int allCount, out int exposedCount)
        {
            return TryComputeDragAreaAtAoA(rocket, null, out drag, out copX, out copY, out allCount, out exposedCount);
        }

        // Generalized 2026-09-06: identical reflection chain as TryComputeDragArea,
        // but optionally builds the alignment matrix from a SYNTHETIC target AoA
        // (degrees) instead of the craft's real current velocity heading. This
        // works because GetDragSurfaces(Matrix2x2) is a pure function of (real
        // current part geometry) x (an alignment matrix) -- the matrix is built
        // from a bare scalar angle, not read internally from the craft's real
        // state. The real 'dragarea'/TryComputeDragArea path derives that scalar
        // from real velocityAngle; this derives an EQUIVALENT scalar that would
        // produce a CHOSEN AoA relative to the craft's real current rotation,
        // using the same AoA convention analysis/aoa_dragarea.py already assumes
        // (aoaDeg = wrap((theta+90) - headingDeg)): solving for the synthetic
        // heading that yields the requested AoA at the craft's real theta, then
        // feeding that into the IDENTICAL formula the real velocity-driven path
        // uses. Lets a full AoA sweep be read from the game's own real drag
        // computation in one command, on a stationary craft, with zero actual
        // maneuvering -- see 'dragareasweep' command. aoaTargetDeg=null
        // reproduces the original real-velocity behavior exactly (backward
        // compatible with every existing caller of TryComputeDragArea).
        static bool TryComputeDragAreaAtAoA(object rocket, float? aoaTargetDeg, out float drag, out float copX, out float copY,
                                        out int allCount, out int exposedCount)
        {
            drag = 0f; copX = 0f; copY = 0f; allCount = 0; exposedCount = 0;
            try
            {
                object aero = Get(rocket, "aero");
                if (aero == null) return false;

                Type matrixType = FindType("Matrix2x2");
                Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
                if (matrixType == null || aeroModuleType == null) return false;

                float rotationInput;
                if (aoaTargetDeg.HasValue)
                {
                    object rb2dForAoa = Get(rocket, "rb2d");
                    float thetaRealDeg = ToF(Get(rb2dForAoa, "rotation"));
                    float syntheticHeadingDeg = thetaRealDeg + 90f - aoaTargetDeg.Value;
                    double syntheticHeadingRad = syntheticHeadingDeg * Math.PI / 180.0;
                    rotationInput = (float)(-(syntheticHeadingRad - Math.PI / 2.0));
                }
                else
                {
                    object dloc = Unwrap(Get(rocket, "location"));
                    object velocity = GetWrapped(dloc, "velocity");
                    double velocityAngle = ToD(Get(velocity, "AngleRadians"));
                    rotationInput = (float)(-(velocityAngle - Math.PI / 2.0));
                }
                object matrix = InvokeStatic(matrixType, "Angle", new Type[] { typeof(float) }, new object[] { rotationInput });
                if (matrix == null) return false;

                MethodInfo getDragSurfaces = aero.GetType().GetMethod("GetDragSurfaces",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                    null, new Type[] { matrixType }, null);
                if (getDragSurfaces == null) return false;

                object allSurfaces;
                try { allSurfaces = getDragSurfaces.Invoke(aero, new object[] { matrix }); }
                catch { return false; }
                if (allSurfaces == null) return false;

                var allEn = allSurfaces as System.Collections.IEnumerable;
                if (allEn != null) foreach (object s in allEn) allCount++;

                object exposedSurfaces = InvokeStatic(aeroModuleType, "GetExposedSurfaces",
                    new Type[] { allSurfaces.GetType() }, new object[] { allSurfaces });
                if (exposedSurfaces == null) return false;
                var exposedEn = exposedSurfaces as System.Collections.IEnumerable;
                if (exposedEn != null) foreach (object s in exposedEn) exposedCount++;

                MethodInfo calcDrag = aeroModuleType.GetMethod("CalculateDragForce",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static,
                    null, new Type[] { exposedSurfaces.GetType() }, null);
                if (calcDrag == null) return false;

                object tupleObj;
                try { tupleObj = calcDrag.Invoke(null, new object[] { exposedSurfaces }); }
                catch { return false; }
                var tuple = (System.ValueTuple<float, Vector2>)tupleObj;
                drag = tuple.Item1;
                copX = tuple.Item2.x;
                copY = tuple.Item2.y;
                return true;
            }
            catch { return false; }
        }

        // Aerodynamic torque magnitude (2026-08-31). Two things needed doing
        // that hadn't been done anywhere else in this file yet:
        //   1. dragCopX/Y in truth.jsonl is in VELOCITY-ALIGNED space, not real
        //      world/scene coordinates -- confirmed via IL long ago (the
        //      "multiply by the non-negated Matrix2x2.Angle" gotcha, C1.2) but
        //      never actually wired into any command. Fixed here: the real
        //      localToWorld rotation is applied before centerOfDrag is used for
        //      anything CoM-relative.
        //   2. Unlike player-commanded rotation (writes angularVelocity DIRECTLY,
        //      ignores moment of inertia entirely -- confirmed, B1.3), real aero
        //      force goes through Unity's own AddForceAtPosition, so predicting
        //      the resulting angular acceleration needs rb2d.inertia -- a stock
        //      Unity Rigidbody2D property, never read by this probe before.
        // KNOWN CAVEAT, not yet handled: if a parachute is deployed,
        // Aero_Rocket.ApplyParachuteDrag mutates BOTH force and cop by reference
        // (confirmed, C1.5/E6.1) -- this does NOT replicate that path, so any
        // validation flight for this must keep the parachute stowed.
        static bool TryComputeAeroTorque(object rocket, out float torqueZ, out float alphaPred,
            out float forceX, out float forceY, out float copWorldX, out float copWorldY,
            out float copAppliedX, out float copAppliedY, out float comX, out float comY,
            out float inertia, out float dragAreaOut, out double densityOut, out float angularDrag)
        {
            torqueZ = 0f; alphaPred = 0f; forceX = 0f; forceY = 0f;
            copWorldX = 0f; copWorldY = 0f; copAppliedX = 0f; copAppliedY = 0f;
            comX = 0f; comY = 0f; inertia = 0f; dragAreaOut = 0f; densityOut = 0.0; angularDrag = 0f;
            try
            {
                object rb2d = Get(rocket, "rb2d");
                if (rb2d == null) return false;
                object worldCoMObj = Get(rb2d, "worldCenterOfMass");
                if (worldCoMObj == null) return false;
                comX = ToF(Get(worldCoMObj, "x"));
                comY = ToF(Get(worldCoMObj, "y"));
                inertia = ToF(Get(rb2d, "inertia"));
                // NEW (2026-09-06, aero_torque closed-loop instability
                // investigation): angularDrag has NEVER been read by this
                // probe before. AddForceAtPosition (what real aero torque
                // goes through) is genuine Unity Rigidbody2D physics, and
                // Unity's real solver applies angularDrag damping every
                // tick -- neither TryComputeAeroTorque's own alphaPred
                // formula (r x F / inertia, hand-derived, not IL-read) nor
                // forward_sim.py's Python replica has ever modeled this.
                // Reading it now to test whether its absence explains the
                // closed-loop runaway a pure-aero-torque replay shows.
                angularDrag = ToF(Get(rb2d, "angularDrag"));

                float dragCopVelX, dragCopVelY;
                int allC, expC;
                bool dragOk = TryComputeDragArea(rocket, out dragAreaOut, out dragCopVelX, out dragCopVelY, out allC, out expC);
                if (!dragOk) return false;

                object dloc = Unwrap(Get(rocket, "location"));
                object velocity = GetWrapped(dloc, "velocity");
                double vx = ToD(Get(velocity, "x"));
                double vy = ToD(Get(velocity, "y"));
                double speedSq = vx * vx + vy * vy;
                double speed = Math.Sqrt(speedSq);
                if (speed < 1e-6) return false;   // no meaningful direction -- drag is ~0 anyway
                double vhatX = vx / speed, vhatY = vy / speed;
                double velocityAngle = ToD(Get(velocity, "AngleRadians"));

                Type matrixType = FindType("Matrix2x2");
                if (matrixType == null) return false;
                // localToWorld is the NON-negated angle -- opposite sign from the
                // "rotate" matrix TryComputeDragArea/GetDragSurfaces uses to build
                // velocity-aligned surfaces in the first place.
                float localToWorldInput = (float)(velocityAngle - Math.PI / 2.0);
                object localToWorldMatrix = InvokeStatic(matrixType, "Angle", new Type[] { typeof(float) }, new object[] { localToWorldInput });
                if (localToWorldMatrix == null) return false;

                MethodInfo mulMethod = matrixType.GetMethod("op_Multiply", BindingFlags.Public | BindingFlags.Static,
                    null, new Type[] { matrixType, typeof(Vector2) }, null);
                if (mulMethod == null) return false;
                object copWorldObj = mulMethod.Invoke(null, new object[] { localToWorldMatrix, new Vector2(dragCopVelX, dragCopVelY) });
                if (!(copWorldObj is Vector2)) return false;
                Vector2 copWorld = (Vector2)copWorldObj;
                copWorldX = copWorld.x; copWorldY = copWorld.y;

                object planet = Unwrap(Get(dloc, "planet"));
                double height = ToD(Get(dloc, "Height"));
                object densityObj = InvokeReturn(planet, "GetAtmosphericDensity", new object[] { height });
                double density = densityObj != null ? ToD(densityObj) : 0.0;
                densityOut = density;

                // Matches AeroModule.ApplyForce's own body exactly (C1.5, confirmed).
                float f = dragAreaOut * 1.5f * (float)speedSq;
                forceX = -(float)vhatX * (f * (float)density);
                forceY = -(float)vhatY * (f * (float)density);

                // Confirmed 20% Lerp toward true CoP (sfs_physics_reference.md 2.3 /
                // sfs_source_reference.md C1.5) -- NOT the full CoP.
                copAppliedX = comX + (copWorldX - comX) * 0.2f;
                copAppliedY = comY + (copWorldY - comY) * 0.2f;

                float rX = copAppliedX - comX;
                float rY = copAppliedY - comY;
                torqueZ = rX * forceY - rY * forceX;              // 2D cross product, r x F
                alphaPred = inertia != 0f ? torqueZ / inertia : float.NaN;
                return true;
            }
            catch (Exception e)
            {
                ProbeMod.Log("[aerotorque] compute error: " + e.Message);
                return false;
            }
        }

        // Lightweight per-tick counterpart to the 'gimbalinfo' command
        // (2026-08-31). Curve keyframes (linear vs. eased -- the actual open
        // question) are STATIC per engine, so they don't belong in per-tick
        // telemetry; this only reads the parts of the confirmed chain that
        // genuinely change every tick (target-setting + MoveTowards timing),
        // so a real flight gives the response ramp automatically without
        // needing 'gimbalinfo' pressed repeatedly.
        //
        // FIXED 2026-09-03 (v0.56.0, then corrected same day): used to
        // return the FIRST engine with hasGimbal==true in part order --
        // wrong on a real multi-engine/multi-stage rocket, since the
        // first gimbaling engine in part order isn't necessarily one
        // that's firing. v0.56.0's first fix compared throttle_Out
        // magnitudes across engines and kept the highest -- functional,
        // but not the RIGHT reason: per the confirmed three-layer control
        // model (sfs_physics_reference.md D2.2), "amount" (throttle_Input)
        // and master ignition are BOTH rocket-wide, broadcast identically
        // to every engine (RecalculateEngineThrottle: throttle_Out =
        // engineOn ? throttle_Input : 0f) -- so throttle_Out only ever
        // differs between engines because of the one genuinely per-engine
        // flag, engineOn. Comparing magnitudes was working by coincidence,
        // not by checking the actual thing that varies. This version reads
        // engineOn directly instead: prefers the first gimbaling engine
        // that is actually ON, and only falls back to the first gimbaling
        // engine found (regardless of state) if none are on at all -- the
        // same degenerate between-stages case the original code always
        // hit, now handled explicitly instead of by accident.
        static bool TryGetPrimaryGimbal(object rocket, out bool gimbalOn, out float throttleOut,
            out float turnAxisInput, out float timeVal, out float targetTimeVal)
        {
            gimbalOn = false; throttleOut = 0f; turnAxisInput = 0f; timeVal = 0f; targetTimeVal = 0f;
            try
            {
                object holder = Get(rocket, "partHolder");
                object parts = Get(holder, "parts");
                var en = parts as System.Collections.IEnumerable;
                if (en == null) return false;

                object firstCandidate = null;
                foreach (object part in en)
                {
                    foreach (object mv in ModuleValues(part))
                    {
                        if (mv.GetType().Name != "EngineModule") continue;
                        bool hasGimbal = ToB(Get(mv, "hasGimbal"));
                        if (!hasGimbal) continue;

                        if (firstCandidate == null) firstCandidate = mv;

                        // The one flag that genuinely varies per engine
                        // (staging, individual toggling) -- NOT amount or
                        // master ignition, which are shared by every engine.
                        bool engineOnNow = ToB(GetWrapped2(Get(mv, "engineOn")));
                        if (!engineOnNow) continue;

                        ReadPrimaryGimbalFields(mv, out gimbalOn, out throttleOut,
                            out turnAxisInput, out timeVal, out targetTimeVal);
                        return true;   // first ON gimbaling engine -- any other ON one would read the same shared throttle/turn-axis anyway
                    }
                }

                if (firstCandidate != null)
                {
                    // No gimbaling engine currently on (e.g. between
                    // stages) -- fall back to the first one found, same
                    // as the pre-fix default state.
                    ReadPrimaryGimbalFields(firstCandidate, out gimbalOn, out throttleOut,
                        out turnAxisInput, out timeVal, out targetTimeVal);
                    return true;
                }
                return false;
            }
            catch (Exception e)
            {
                ProbeMod.Log("[gimbal-telemetry] compute error: " + e.Message);
                return false;
            }
        }

        // Small shared reader used by TryGetPrimaryGimbal's two return
        // paths (an ON engine, or the between-stages fallback) so the
        // five-field read logic exists in exactly one place.
        static void ReadPrimaryGimbalFields(object mv, out bool gimbalOn, out float throttleOut,
            out float turnAxisInput, out float timeVal, out float targetTimeVal)
        {
            gimbalOn = ToB(GetWrapped2(Get(mv, "gimbalOn")));
            throttleOut = ToF(GetWrapped2(Get(mv, "throttle_Out")));
            turnAxisInput = ToF(GetWrapped2(Get(mv, "turnAxis_Input")));
            object gimbal = Get(mv, "gimbal");
            timeVal = ToF(GetWrapped2(Get(gimbal, "time")));
            targetTimeVal = ToF(GetWrapped2(Get(gimbal, "targetTime")));
        }

        // Parachute drag (2026-09-01). Extends TryComputeAeroTorque's exact
        // logic (same matrix rotation, same Lerp) with the confirmed
        // Aero_Rocket.ApplyParachuteDrag compounding step, run AFTER the
        // normal Lerp -- NOT a bypass, confirmed via the real call site
        // (sfs_source_reference.md C1.11). For each deployed chute
        // (targetState 1=partial/2=full, 0=stowed skipped): chuteDrag =
        // GetPointVelocity(chute.position).sqrMagnitude * chute.drag.Evaluate
        // (chute.state) -- the ONE rotation-aware path in the whole aero
        // chain -- then cop/force update via a force-weighted average,
        // compounding sequentially across multiple chutes. chuteDrag has no
        // density term of its own; density is applied once, uniformly, to
        // the combined total at the end (matching the real order of
        // operations).
        static bool TryComputeParachuteDrag(object rocket, out float torqueZ, out float alphaPred,
            out float forceX, out float forceY, out float copAppliedX, out float copAppliedY,
            out float comX, out float comY, out float inertia, out float dragAreaOut,
            out float chuteDragTotal, out int numChutesActive)
        {
            torqueZ = 0f; alphaPred = 0f; forceX = 0f; forceY = 0f;
            copAppliedX = 0f; copAppliedY = 0f; comX = 0f; comY = 0f;
            inertia = 0f; dragAreaOut = 0f; chuteDragTotal = 0f; numChutesActive = 0;
            try
            {
                object rb2d = Get(rocket, "rb2d");
                if (rb2d == null) return false;
                object worldCoMObj = Get(rb2d, "worldCenterOfMass");
                if (worldCoMObj == null) return false;
                comX = ToF(Get(worldCoMObj, "x"));
                comY = ToF(Get(worldCoMObj, "y"));
                inertia = ToF(Get(rb2d, "inertia"));

                float dragCopVelX, dragCopVelY;
                int allC, expC;
                bool dragOk = TryComputeDragArea(rocket, out dragAreaOut, out dragCopVelX, out dragCopVelY, out allC, out expC);
                if (!dragOk) return false;

                object dloc = Unwrap(Get(rocket, "location"));
                object velocity = GetWrapped(dloc, "velocity");
                double vx = ToD(Get(velocity, "x"));
                double vy = ToD(Get(velocity, "y"));
                double speedSq = vx * vx + vy * vy;
                double speed = Math.Sqrt(speedSq);
                if (speed < 1e-6) return false;
                double vhatX = vx / speed, vhatY = vy / speed;
                double velocityAngle = ToD(Get(velocity, "AngleRadians"));

                Type matrixType = FindType("Matrix2x2");
                if (matrixType == null) return false;
                float localToWorldInput = (float)(velocityAngle - Math.PI / 2.0);
                object localToWorldMatrix = InvokeStatic(matrixType, "Angle", new Type[] { typeof(float) }, new object[] { localToWorldInput });
                if (localToWorldMatrix == null) return false;

                MethodInfo mulMethod = matrixType.GetMethod("op_Multiply", BindingFlags.Public | BindingFlags.Static,
                    null, new Type[] { matrixType, typeof(Vector2) }, null);
                if (mulMethod == null) return false;
                object copWorldObj = mulMethod.Invoke(null, new object[] { localToWorldMatrix, new Vector2(dragCopVelX, dragCopVelY) });
                if (!(copWorldObj is Vector2)) return false;
                Vector2 copWorld = (Vector2)copWorldObj;

                object planet = Unwrap(Get(dloc, "planet"));
                double height = ToD(Get(dloc, "Height"));
                object densityObj = InvokeReturn(planet, "GetAtmosphericDensity", new object[] { height });
                double density = densityObj != null ? ToD(densityObj) : 0.0;

                // f: the shared pre-direction, pre-density magnitude scalar --
                // confirmed identical to the 'force' ref-param ApplyParachuteDrag
                // receives and mutates.
                float f = dragAreaOut * 1.5f * (float)speedSq;

                // Normal §2.3 Lerp -- confirmed to run BEFORE the parachute call,
                // not bypassed by it.
                float copX = comX + (copWorld.x - comX) * 0.2f;
                float copY = comY + (copWorld.y - comY) * 0.2f;

                // -- ApplyParachuteDrag, confirmed compounding logic --
                Type worldViewType = FindType("SFS.World.WorldView");
                object mainView = worldViewType != null ? Get(worldViewType, "main") : null;
                object velOffsetWrapped = mainView != null ? Get(mainView, "velocityOffset") : null;
                object velOffsetVal = velOffsetWrapped != null ? GetWrapped2(velOffsetWrapped) : null;
                double offX = velOffsetVal != null ? ToD(Get(velOffsetVal, "x")) : 0.0;
                double offY = velOffsetVal != null ? ToD(Get(velOffsetVal, "y")) : 0.0;

                object holder = Get(rocket, "partHolder");
                object parts = Get(holder, "parts");
                var partsEn = parts as System.Collections.IEnumerable;
                if (partsEn != null)
                {
                    foreach (object part in partsEn)
                    {
                        foreach (object mv in ModuleValues(part))
                        {
                            if (mv.GetType().Name != "ParachuteModule") continue;
                            float targetState = ToF(GetWrapped2(Get(mv, "targetState")));
                            if (targetState != 1f && targetState != 2f) continue;   // 0 = stowed

                            object chuteTransform = Get(mv, "parachute");
                            if (chuteTransform == null) continue;
                            object posObj = Get(chuteTransform, "position");
                            if (posObj == null) continue;
                            float chutePosX = ToF(Get(posObj, "x"));
                            float chutePosY = ToF(Get(posObj, "y"));

                            MethodInfo gpvMethod = rb2d.GetType().GetMethod("GetPointVelocity", new Type[] { typeof(Vector2) });
                            if (gpvMethod == null) continue;
                            object localVelObj = gpvMethod.Invoke(rb2d, new object[] { new Vector2(chutePosX, chutePosY) });
                            if (!(localVelObj is Vector2)) continue;
                            Vector2 localVel = (Vector2)localVelObj;

                            // WorldView.ToGlobalVelocity(local) = velocityOffset + local (Double2 + Vector2)
                            double gVelX = offX + localVel.x;
                            double gVelY = offY + localVel.y;
                            double chuteSqrMag = gVelX * gVelX + gVelY * gVelY;

                            object curveObj = Get(mv, "drag");
                            if (curveObj == null) continue;
                            float stateVal = ToF(GetWrapped2(Get(mv, "state")));
                            object evalResult = InvokeReturn(curveObj, "Evaluate", new object[] { stateVal });
                            float curveVal = evalResult != null ? ToF(evalResult) : 0f;

                            float chuteDrag = (float)chuteSqrMag * curveVal;
                            if (chuteDrag <= 0f) continue;

                            copX = (copX * f + chutePosX * chuteDrag) / (f + chuteDrag);
                            copY = (copY * f + chutePosY * chuteDrag) / (f + chuteDrag);
                            f = f + chuteDrag;
                            chuteDragTotal += chuteDrag;
                            numChutesActive++;
                        }
                    }
                }

                forceX = -(float)vhatX * (f * (float)density);
                forceY = -(float)vhatY * (f * (float)density);
                copAppliedX = copX; copAppliedY = copY;

                float rX = copAppliedX - comX;
                float rY = copAppliedY - comY;
                torqueZ = rX * forceY - rY * forceX;
                alphaPred = inertia != 0f ? torqueZ / inertia : float.NaN;
                return true;
            }
            catch (Exception e)
            {
                ProbeMod.Log("[parachutedrag] compute error: " + e.Message);
                return false;
            }
        }

        // Item 1/2 from the heat gap list (2026-08-30): per-part ExposedSurface
        // and real per-part Temperature/HeatTolerance/IsHeatShield, every tick.
        // Recomputes GetDragSurfaces->GetExposedSurfaces independently of
        // TryComputeDragArea above (a second reflection pass, not shared -- kept
        // simple/separate rather than risking the already-working dragArea path)
        // and tallies the REAL per-owner exposed width (Sum of s.line.end.x -
        // s.line.start.x per owner, exactly matching HeatManager.ApplyHeat's own
        // accumulator) instead of substituting whole-rocket dragArea, which was
        // the single biggest source of error in the first accumulation-model
        // validation (2026-08-30, ~27% peak-magnitude error). Walks every part,
        // resolves its real heat owner (HeatModule if present, else the Part
        // itself -- same resolution GetHeatState uses), and reads Temperature/
        // HeatTolerance/IsHeatShield off that owner via the property (not the
        // differently-named backing field). +-Infinity sentinels are preserved
        // as explicit strings, not coerced to null, so the sign-mismatch bug
        // (see HeatManager.md) is directly observable in real telemetry instead
        // of being silently hidden by JSON null-coercion.
        static string GetHeatPartsArray(object rocket)
        {
            var items = new List<string>();
            try
            {
                object aero = Get(rocket, "aero");
                var widthByOwner = new Dictionary<object, float>(ReferenceEqualityComparer.Instance);
                if (aero != null)
                {
                    Type matrixType = FindType("Matrix2x2");
                    Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
                    if (matrixType != null && aeroModuleType != null)
                    {
                        object dloc = Unwrap(Get(rocket, "location"));
                        object velocity = GetWrapped(dloc, "velocity");
                        double velocityAngle = ToD(Get(velocity, "AngleRadians"));
                        float rotationInput = (float)(-(velocityAngle - Math.PI / 2.0));
                        object matrix = InvokeStatic(matrixType, "Angle", new Type[] { typeof(float) }, new object[] { rotationInput });
                        if (matrix != null)
                        {
                            MethodInfo getDragSurfaces = aero.GetType().GetMethod("GetDragSurfaces",
                                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                                null, new Type[] { matrixType }, null);
                            object allSurfaces = null;
                            if (getDragSurfaces != null)
                            {
                                try { allSurfaces = getDragSurfaces.Invoke(aero, new object[] { matrix }); }
                                catch { allSurfaces = null; }
                            }
                            if (allSurfaces != null)
                            {
                                object exposedSurfaces = InvokeStatic(aeroModuleType, "GetExposedSurfaces",
                                    new Type[] { allSurfaces.GetType() }, new object[] { allSurfaces });

                                // CONFIRMED via real IL 2026-08-30 (root-caused the ~50%
                                // uniform overprediction in the first per-part heat
                                // validation): the drag-path exposed list is NOT what
                                // HeatManager.ApplyHeat actually sees. AeroModule
                                // .FixedUpdate_Reentry_And_Heating filters it through TWO
                                // heating-only functions BEFORE tallying ExposedSurface:
                                //   RemoveHighSlopeSurfaces(list, 5.0f) -- keeps only
                                //     |dy/dx|<5.0 AND dx>0.1 (10x stricter than drag's
                                //     dx>0.01 cull, and excludes steep segments drag keeps).
                                //   ApplyProtectionZone(list) -- a real geometric shadow-
                                //     occlusion pass: wherever the outline has a >0.1-unit
                                //     y-step, nearby segments within a min(gap*0.2,0.4)-wide
                                //     zone are removed or clipped, modeling a protruding
                                //     part shielding recessed geometry from airflow.
                                // Calling the REAL private static methods via reflection
                                // rather than reimplementing this geometry -- especially
                                // ApplyProtectionZone -- risks a new bug; the game's own
                                // code is ground truth by construction.
                                if (exposedSurfaces != null)
                                {
                                    MethodInfo removeHighSlope = aeroModuleType.GetMethod("RemoveHighSlopeSurfaces",
                                        BindingFlags.NonPublic | BindingFlags.Static, null,
                                        new Type[] { exposedSurfaces.GetType(), typeof(float) }, null);
                                    if (removeHighSlope != null)
                                    {
                                        try { exposedSurfaces = removeHighSlope.Invoke(null, new object[] { exposedSurfaces, 5.0f }); }
                                        catch (Exception e) { ProbeMod.Log("[heat-parts] RemoveHighSlopeSurfaces threw: " + e.Message); }
                                    }
                                    MethodInfo applyProtectionZone = aeroModuleType.GetMethod("ApplyProtectionZone",
                                        BindingFlags.NonPublic | BindingFlags.Static, null,
                                        new Type[] { exposedSurfaces.GetType() }, null);
                                    if (applyProtectionZone != null)
                                    {
                                        try { applyProtectionZone.Invoke(null, new object[] { exposedSurfaces }); }
                                        catch (Exception e) { ProbeMod.Log("[heat-parts] ApplyProtectionZone threw: " + e.Message); }
                                    }
                                }

                                var sEn = exposedSurfaces as System.Collections.IEnumerable;
                                if (sEn != null)
                                {
                                    foreach (object s in sEn)
                                    {
                                        object owner = Get(s, "owner");
                                        if (owner == null) continue;
                                        object lineObj = Get(s, "line");
                                        object start = Get(lineObj, "start");
                                        object end = Get(lineObj, "end");
                                        float sx = ToF(Get(start, "x"));
                                        float ex = ToF(Get(end, "x"));
                                        float dx = ex - sx;
                                        float cur;
                                        widthByOwner.TryGetValue(owner, out cur);
                                        widthByOwner[owner] = cur + dx;
                                    }
                                }
                            }
                        }
                    }
                }

                object holder = Get(rocket, "partHolder");
                object parts = Get(holder, "parts");
                var partsEn = parts as System.Collections.IEnumerable;
                if (partsEn != null)
                {
                    foreach (object part in partsEn)
                    {
                        object owner = null;
                        foreach (object mv in ModuleValues(part))
                        {
                            if (mv.GetType().Name == "HeatModule") { owner = mv; break; }
                        }
                        if (owner == null) owner = part;

                        string name = "?";
                        float temp = 0f, tol = 0f;
                        bool shield = false;
                        try { name = (string)Get(owner, "Name"); } catch { }
                        try { temp = ToF(Get(owner, "Temperature")); } catch { }
                        try { tol = ToF(Get(owner, "HeatTolerance")); } catch { }
                        try { shield = ToB(Get(owner, "IsHeatShield")); } catch { }

                        float width = 0f;
                        widthByOwner.TryGetValue(owner, out width);

                        var sb = new StringBuilder();
                        sb.Append("{\"name\":").Append(Q(name));
                        sb.Append(",\"temperature\":").Append(NumOrInf(temp));
                        sb.Append(",\"heatTolerance\":").Append(Num(tol));
                        sb.Append(",\"isHeatShield\":").Append(shield ? "true" : "false");
                        sb.Append(",\"exposedSurface\":").Append(Num(width));
                        sb.Append("}");
                        items.Add(sb.ToString());
                    }
                }
            }
            catch (Exception e)
            {
                ProbeMod.Log("[heat-parts] error: " + e.Message);
            }
            return "[" + string.Join(",", items.ToArray()) + "]";
        }

        // +-Infinity are real sentinel values in this system (DissipateHeat's
        // "fully cooled" marker, PartSave.temperature's "never heated" default --
        // see HeatManager.md's open sign-mismatch question), not error states.
        // Num()'s ToString("R") would emit the literal word "Infinity", which is
        // NOT valid JSON -- encoded as an explicit string instead so the sentinel
        // is visible in telemetry rather than silently corrupting the file or
        // being coerced away.
        static string NumOrInf(float v)
        {
            if (float.IsPositiveInfinity(v)) return "\"+Inf\"";
            if (float.IsNegativeInfinity(v)) return "\"-Inf\"";
            return Num(v);
        }

        // Generic dot-path walker for scoped telemetry field specs (v0.29),
        // e.g. "rb2d.mass" or "location.velocity.x". Starts from the given
        // root (the active rocket, currently the only supported root) and
        // chases each segment via the SAME Get()+GetWrapped2 semantics already
        // used everywhere else in this file -- not a new resolution mechanism,
        // just the existing one driven by a string instead of hardcoded per
        // field. Unwrapping after every hop is a harmless no-op on values that
        // aren't wrapper types (Composed_Float, Double_Reference, etc.).
        static object ResolvePath(object root, string path)
        {
            object cur = root;
            foreach (string seg in path.Split('.'))
            {
                if (cur == null) return null;
                cur = GetWrapped2(Get(cur, seg));
            }
            return cur;
        }

        // Registry of named "computed" fields for scoped telemetry (v0.29) --
        // fields that need real logic first, not just a property read (e.g.
        // dragArea needs the velocity-derived rotation matrix). Appends the
        // field's own named sub-keys directly into the caller's StringBuilder
        // and returns true, or returns false for an unknown name so the caller
        // can report it. Kept as a switch (not a delegate dictionary) to match
        // this file's existing style -- no DI, no registries elsewhere.
        // ADDING A NEW COMPUTED FIELD: add one case here reusing an existing
        // helper -- SumEnabledTorque, CountFiringThrusters, GetHeatState,
        // FuelByStage, GetPredictedOrbit, and GetEngineArray all already
        // exist and could be wired in exactly the same way as "dragArea" below,
        // with no new physics/reflection code needed, just a rebuild.
        static bool AppendComputedField(string name, object rocket, StringBuilder sb)
        {
            switch (name)
            {
                case "dragArea":
                {
                    float drag, copX, copY; int allC, expC;
                    bool ok = TryComputeDragArea(rocket, out drag, out copX, out copY, out allC, out expC);
                    sb.Append(",\"dragArea\":").Append(ok ? Num(drag) : "null");
                    sb.Append(",\"dragCopX\":").Append(ok ? Num(copX) : "null");
                    sb.Append(",\"dragCopY\":").Append(ok ? Num(copY) : "null");
                    sb.Append(",\"dragSurfaces\":").Append(allC);
                    sb.Append(",\"dragExposed\":").Append(expC);
                    return true;
                }
                case "engines":
                {
                    List<string> engines = GetEngineArray(rocket);
                    sb.Append(",\"engines\":[").Append(string.Join(",", engines.ToArray())).Append("]");
                    return true;
                }
                case "heatParts":
                {
                    sb.Append(",\"heatParts\":").Append(GetHeatPartsArray(rocket));
                    return true;
                }
                case "aeroTorque":
                {
                    // For a real validation flight: "telemetry on computed:aeroTorque"
                    // (or combined with rot/angv via their own plain reflection paths,
                    // e.g. "telemetry on rb2d.rotation,rb2d.angularVelocity,computed:aeroTorque")
                    // records predicted torque/alpha every tick, to compare against the
                    // REAL angularVelocity finite-difference afterward -- same pattern as
                    // the RCS force validation. Engine off + RCS off + no parachute
                    // deployed is required to isolate aero torque cleanly (see
                    // TryComputeAeroTorque's header comment for the parachute caveat).
                    float torqueZ, alphaPred, fX, fY, copWX, copWY, copAX, copAY, comXo, comYo, inertiaO, dragAO, angularDragO;
                    double densityO;
                    bool ok = TryComputeAeroTorque(rocket, out torqueZ, out alphaPred, out fX, out fY,
                        out copWX, out copWY, out copAX, out copAY, out comXo, out comYo, out inertiaO, out dragAO, out densityO, out angularDragO);
                    sb.Append(",\"aeroTorque\":").Append(ok ? Num(torqueZ) : "null");
                    sb.Append(",\"aeroAlphaDeg\":").Append(ok ? Num(alphaPred * 57.29578f) : "null");
                    sb.Append(",\"rbInertia\":").Append(ok ? Num(inertiaO) : "null");
                    sb.Append(",\"rbAngularDrag\":").Append(ok ? Num(angularDragO) : "null");
                    return true;
                }
                case "gimbal":
                {
                    // "telemetry on computed:gimbal" (combine with turnAxis for
                    // the commanded input, e.g. "telemetry on
                    // arrowkeys.turnAxis,computed:gimbal"). Records the confirmed
                    // target-setting + MoveTowards timing (sfs_source_reference.md
                    // §B1.10) every tick -- the response ramp should show time
                    // reaching targetTime in exactly animationTime seconds, linearly.
                    // Curve shape (linear vs eased) is NOT here -- that's static, use
                    // the one-shot 'gimbalinfo' command for that.
                    bool gOn; float gThrOut, gTurnIn, gTime, gTarget;
                    bool gok = TryGetPrimaryGimbal(rocket, out gOn, out gThrOut, out gTurnIn, out gTime, out gTarget);
                    sb.Append(",\"gimbalOn\":").Append(gok ? (gOn ? "true" : "false") : "null");
                    sb.Append(",\"gimbalThrottleOut\":").Append(gok ? Num(gThrOut) : "null");
                    sb.Append(",\"gimbalTurnAxisInput\":").Append(gok ? Num(gTurnIn) : "null");
                    sb.Append(",\"gimbalTime\":").Append(gok ? Num(gTime) : "null");
                    sb.Append(",\"gimbalTargetTime\":").Append(gok ? Num(gTarget) : "null");
                    return true;
                }
                case "torque":
                {
                    // Added 2026-09-06 to test whether a TorqueModule's torque
                    // expression is parametric on live state (e.g. throttle_Out)
                    // rather than a fixed per-part constant -- SumEnabledTorque
                    // already existed (used by full-mode's BuildInputsSample) but
                    // was never wired into scoped telemetry. Compare this LIVE
                    // per-tick value against getforwardstartinfo's pre-ignition
                    // torqueEffectiveRaw snapshot for the same craft.
                    float torqueLive = SumEnabledTorque(rocket);
                    sb.Append(",\"torqueEffectiveLive\":").Append(Num(torqueLive));
                    return true;
                }
                case "parachuteDrag":
                {
                    // "telemetry on rb2d.angularVelocity,computed:parachuteDrag"
                    // for a real deployed-chute validation flight, same pattern as
                    // aeroTorque. chutesActive lets you filter to exactly the ticks
                    // where a chute was actually contributing (0 = harmlessly
                    // reduces to plain aero torque, still useful as a control).
                    float pdTorque, pdAlpha, pdFx, pdFy, pdCopX, pdCopY, pdComX, pdComY, pdInertia, pdDragArea, pdChuteDrag;
                    int pdNumChutes;
                    bool pdOk = TryComputeParachuteDrag(rocket, out pdTorque, out pdAlpha, out pdFx, out pdFy,
                        out pdCopX, out pdCopY, out pdComX, out pdComY, out pdInertia, out pdDragArea,
                        out pdChuteDrag, out pdNumChutes);
                    sb.Append(",\"parachuteTorque\":").Append(pdOk ? Num(pdTorque) : "null");
                    sb.Append(",\"parachuteAlphaDeg\":").Append(pdOk ? Num(pdAlpha * 57.29578f) : "null");
                    sb.Append(",\"parachuteChutesActive\":").Append(pdOk ? pdNumChutes.ToString() : "null");
                    sb.Append(",\"parachuteRbInertia\":").Append(pdOk ? Num(pdInertia) : "null");
                    sb.Append(",\"parachuteForceX\":").Append(pdOk ? Num(pdFx) : "null");
                    sb.Append(",\"parachuteForceY\":").Append(pdOk ? Num(pdFy) : "null");
                    return true;
                }
                default:
                    return false;
            }
        }

        static StringBuilder Header()
        {
            var sb = new StringBuilder();
            sb.Append("{\n");
            sb.Append("  \"gameVersion\": ").Append(Q(Application.version)).Append(",\n");
            sb.Append("  \"fixedDeltaTime\": ").Append(Time.fixedDeltaTime.ToString("R")).Append(",\n");
            sb.Append("  \"deltaTime\": ").Append(Time.deltaTime.ToString("R")).Append(",\n");
            sb.Append("  \"timeScale\": ").Append(Time.timeScale.ToString("R")).Append(",\n");
            return sb;
        }

        static void Write(string file, StringBuilder sb, string note)
        {
            try
            {
                File.WriteAllText(Path.Combine(ProbeMod.OutDir ?? ".", file), sb.ToString());
                ProbeMod.Log("WROTE " + file + " (" + sb.Length + " bytes) " + note);
            }
            catch (Exception e) { ProbeMod.Log("write " + file + " failed: " + e); }
        }

        static object FindComponent(string typeName)
        {
            try
            {
                Type t = FindType(typeName);
                if (t == null) return null;
                UnityEngine.Object[] f = Resources.FindObjectsOfTypeAll(t);
                return (f == null || f.Length == 0) ? null : f[0];
            }
            catch { return null; }
        }

        static string Describe(object o)
        {
            if (o == null) return "null";
            var c = o as System.Collections.ICollection;
            return o.GetType().Name + (c != null ? "[" + c.Count + "]" : "");
        }

        static Type FindType(string full)
        {
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type t = null;
                try { t = a.GetType(full, false); } catch { }
                if (t != null) return t;
            }
            return null;
        }

        internal static object Get(object o, string member)
        {
            if (o == null) return null;
            Type t = o as Type ?? o.GetType();
            object target = (o is Type) ? null : o;
            var flags = BindingFlags.Public | BindingFlags.NonPublic |
                        (target == null ? BindingFlags.Static : BindingFlags.Instance);
            var f = t.GetField(member, flags);
            if (f != null) return f.GetValue(target);
            var p = t.GetProperty(member, flags);
            if (p != null) { try { return p.GetValue(target, null); } catch { return null; } }
            return null;
        }

        static string Q(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                else if (c == '\n') sb.Append("\\n");
                else if (c < 32) sb.Append("\\u").Append(((int)c).ToString("x4"));
                else sb.Append(c);
            }
            return sb.Append('"').ToString();
        }

        static string DumpCollection(object coll)
        {
            if (coll == null) return "null";
            var items = new List<string>();
            var en = coll as System.Collections.IEnumerable;
            if (en == null) return Dump(coll, 0);
            foreach (var item in en)
            {
                object v = item;
                var it = v == null ? null : v.GetType();
                if (it != null && it.IsGenericType &&
                    it.GetGenericTypeDefinition() == typeof(KeyValuePair<,>))
                    v = Get(v, "Value");
                items.Add(Dump(v, 0));
            }
            return "[\n    " + string.Join(",\n    ", items.ToArray()) + "\n  ]";
        }

        static string Dump(object o, int depth)
        {
            if (o == null) return "null";
            Type t = o.GetType();
            if (o is string) return Q((string)o);
            if (o is bool) return ((bool)o) ? "true" : "false";
            if (t.IsPrimitive) return Convert.ToDouble(o).ToString("R");
            if (t.IsEnum) return Q(o.ToString());
            if (o is Vector2) { var v = (Vector2)o; return "{\"x\":" + v.x.ToString("R") + ",\"y\":" + v.y.ToString("R") + "}"; }
            if (depth > 3) return Q(t.Name);

            if (o is System.Collections.IEnumerable)
            {
                var els = new List<string>(); int n = 0;
                foreach (var e in (System.Collections.IEnumerable)o)
                { els.Add(Dump(e, depth + 1)); if (++n >= 40) break; }
                if (els.Count > 0) return "[" + string.Join(", ", els.ToArray()) + "]";
            }

            var parts = new List<string>();
            foreach (var f in t.GetFields(BindingFlags.Public | BindingFlags.Instance))
            {
                if (typeof(Delegate).IsAssignableFrom(f.FieldType)) continue;
                if (f.Name == "rocket" || f.Name == "Rocket") continue;
                object v;
                try { v = f.GetValue(o); } catch { continue; }
                if (v is UnityEngine.Object && !(v is MonoBehaviour)) continue;
                parts.Add(Q(f.Name) + ": " + Dump(v, depth + 1));
            }
            foreach (var p in t.GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (p.GetIndexParameters().Length > 0) continue;
                if (!IsSimple(p.PropertyType)) continue;
                object v;
                try { v = p.GetValue(o, null); } catch { continue; }
                parts.Add(Q(p.Name) + ": " + Dump(v, depth + 1));
            }
            if (t.Name == "Part")
            {
                var mf = t.GetField("modules", BindingFlags.NonPublic | BindingFlags.Instance);
                object modules = mf != null ? mf.GetValue(o) : null;
                var en = modules as System.Collections.IEnumerable;
                if (en != null)
                {
                    var modParts = new List<string>();
                    foreach (object kv in en)
                    {
                        object mv = Get(kv, "Value");
                        if (mv == null) continue;
                        modParts.Add(Q(mv.GetType().Name) + ": " + Dump(mv, depth + 1));
                    }
                    if (modParts.Count > 0)
                        parts.Add(Q("modules") + ": {" + string.Join(", ", modParts.ToArray()) + "}");
                }
            }
            if (parts.Count == 0) return Q(t.Name);
            return "{" + string.Join(", ", parts.ToArray()) + "}";
        }

        static bool IsSimple(Type t)
        {
            return t == typeof(string) || t == typeof(bool) || t.IsPrimitive
                || t == typeof(double) || t == typeof(float) || t.IsEnum;
        }
    }

    // ---------- dragArea geometry capture (v0.25) ----------
    //
    // Captures Part.surfacesFast the instant the game's OWN code populates it,
    // via a Harmony Postfix on Part.InitializePart() -- rather than trying to
    // trigger population ourselves (both prior reflection-based attempts at
    // that failed; see docs/sfs_physics_reference.md 7.1 and the dead-ends in
    // session-2026-08-26-gpu-session-1.md).
    //
    // Confirmed via IL (2026-08-26, monodis on Assembly-CSharp.dll): Part.
    // InitializePart() takes ZERO arguments -- not InitializePart(bool) as an
    // earlier research pass claimed. It unconditionally does:
    //   GetComponentsInChildren<I_InitializePartModule>(true) -> sort by
    //   .Priority -> call .Initialize() on each, every single call, no
    //   internal "already done" skip-gate. So this method is safe and cheap
    //   to observe repeatedly -- if the game calls it again later (revert,
    //   respawn, etc.) our cache just refreshes with new geometry.
    //
    // ConditionalWeakTable keys on the live Part instance by reference
    // identity and doesn't keep it alive or leak once the part is
    // destroyed/GC'd.
    public static class GeometryCapture
    {
        public class Captured
        {
            public List<Vector2[]> Loops = new List<Vector2[]>();
            public List<bool> LoopFlags = new List<bool>();
            public int CaptureCount;   // how many times we've observed this part re-init
        }

        static readonly ConditionalWeakTable<object, Captured> Cache =
            new ConditionalWeakTable<object, Captured>();

        // Called from the Harmony postfix -- runs inside the game's own call
        // stack, immediately after real game code. Everything here is
        // defensive: nothing is ever allowed to throw back out, since an
        // uncaught exception at this point risks corrupting that call.
        public static void OnPartInitialized(object partInstance)
        {
            try
            {
                if (partInstance == null) return;

                foreach (object mv in Probe.ModuleValues(partInstance))
                {
                    if (mv.GetType().Name != "SurfaceData") continue;
                    object fast = Probe.Get(mv, "surfacesFast");
                    var sen = fast as System.Collections.IEnumerable;
                    if (sen == null) return;

                    var loops = new List<Vector2[]>();
                    var flags = new List<bool>();
                    foreach (object surf in sen)
                    {
                        object pts = Probe.Get(surf, "points");
                        bool loop = Probe.ToB(Probe.Get(surf, "loop"));
                        var pen = pts as System.Collections.IEnumerable;
                        var list = new List<Vector2>();
                        if (pen != null)
                            foreach (object p in pen)
                                if (p is Vector2) list.Add((Vector2)p);
                        if (list.Count == 0) continue;   // don't record an empty loop
                        loops.Add(list.ToArray());
                        flags.Add(loop);
                    }

                    if (loops.Count == 0) return;   // nothing real captured yet, skip

                    Captured existing;
                    if (Cache.TryGetValue(partInstance, out existing))
                    {
                        existing.Loops = loops;
                        existing.LoopFlags = flags;
                        existing.CaptureCount++;
                    }
                    else
                    {
                        Cache.Add(partInstance, new Captured
                        {
                            Loops = loops,
                            LoopFlags = flags,
                            CaptureCount = 1
                        });
                    }
                    return;
                }
            }
            catch (Exception e)
            {
                try { ProbeMod.Log("[geometry-capture] error: " + e.Message); } catch { }
            }
        }

        public static bool TryGet(object partInstance, out Captured c)
        {
            c = null;
            if (partInstance == null) return false;
            return Cache.TryGetValue(partInstance, out c);
        }
    }

    // Manual (non-attribute) Harmony patching -- consistent with the rest of
    // this file, which never references SFS.* types at compile time. Targets
    // exactly SFS.Parts.Part.InitializePart(), confirmed via IL to be a
    // single method with no overloads (zero arguments).
    public static class GeometryPatches
    {
        // Isolates whether the geometry-capture failure is specific to
        // Part.InitializePart(), or a total environment-wide Harmony/
        // MonoMod incompatibility. Patches a trivial no-op method in OUR
        // OWN assembly -- the simplest possible case, eliminating any
        // cross-assembly (Assembly-CSharp.dll) complexity from the test.
        public static void TrivialNoOp() { }
        static int trivialCallCount;
        static void TrivialNoOpPostfix() { trivialCallCount++; }

        public static bool TestTrivialPatch()
        {
            try
            {
                var harmony = new HarmonyLib.Harmony("sfs_probe.trivial_test");
                MethodInfo target = typeof(GeometryPatches).GetMethod(nameof(TrivialNoOp),
                    BindingFlags.Public | BindingFlags.Static);
                MethodInfo postfixMethod = typeof(GeometryPatches).GetMethod(nameof(TrivialNoOpPostfix),
                    BindingFlags.NonPublic | BindingFlags.Static);
                harmony.Patch(target, postfix: new HarmonyLib.HarmonyMethod(postfixMethod));
                // Actually call it once to confirm the postfix really fires,
                // not just that Patch() returned without throwing.
                trivialCallCount = 0;
                TrivialNoOp();
                return trivialCallCount == 1;
            }
            catch (Exception e)
            {
                ProbeMod.Log("[trivial-patch-test] FAILED: " + e.GetType().FullName + ": " + e.Message);
                return false;
            }
        }

        public static bool Apply(HarmonyLib.Harmony harmony)
        {
            try
            {
                Type partType = FindPartType();
                if (partType == null)
                {
                    ProbeMod.Log("[geometry-capture] FAILED: could not resolve SFS.Parts.Part");
                    return false;
                }

                MethodInfo target = partType.GetMethod("InitializePart",
                    BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance,
                    null, Type.EmptyTypes, null);
                if (target == null)
                {
                    ProbeMod.Log("[geometry-capture] FAILED: Part.InitializePart() not found " +
                                 "(signature may have changed since this was verified)");
                    return false;
                }

                MethodInfo postfixMethod = typeof(GeometryPatches).GetMethod(nameof(Postfix),
                    BindingFlags.Static | BindingFlags.NonPublic);
                if (postfixMethod == null)
                {
                    ProbeMod.Log("[geometry-capture] FAILED: could not resolve Postfix MethodInfo via reflection");
                    return false;
                }

                var postfix = new HarmonyLib.HarmonyMethod(postfixMethod);

                try
                {
                    harmony.Patch(target, postfix: postfix);
                }
                catch (HarmonyLib.HarmonyException he)
                {
                    // Under Mono, HarmonyException carries the exact failing IL
                    // instruction (confirmed via the official HarmonyLib docs) --
                    // GetErrorIndex()/GetInstructions() pinpoint it instead of
                    // just the generic wrapped message. v0.25.2 found these come
                    // back empty (-1, 0) for THIS failure, meaning it happens
                    // before IL is even generated -- so this adds the inner
                    // exception's own STACK TRACE, which is the only remaining
                    // way to see which internal Harmony/MonoMod method actually
                    // threw the NullReferenceException.
                    string detail;
                    try
                    {
                        int idx = he.GetErrorIndex();
                        var instrs = he.GetInstructions();
                        var sb2 = new StringBuilder();
                        sb2.Append("errorIndex=").Append(idx);
                        sb2.Append(" totalInstructions=").Append(instrs != null ? instrs.Count : -1);
                        if (instrs != null && idx >= 0)
                        {
                            int lo = Math.Max(0, idx - 3);
                            int hi = Math.Min(instrs.Count - 1, idx + 3);
                            sb2.Append(" context=[");
                            for (int k = lo; k <= hi; k++)
                            {
                                if (k > lo) sb2.Append(" | ");
                                if (k == idx) sb2.Append(">>>");
                                sb2.Append(instrs[k]);
                            }
                            sb2.Append("]");
                        }

                        Exception deepest = he;
                        while (deepest.InnerException != null) deepest = deepest.InnerException;
                        sb2.Append("\n    deepest=").Append(deepest.GetType().FullName);
                        sb2.Append("\n    deepestStackTrace=").Append(deepest.StackTrace ?? "(null)");

                        detail = sb2.ToString();
                    }
                    catch (Exception diagEx) { detail = "(couldn't extract IL detail: " + diagEx.Message + ")"; }

                    ProbeMod.Log("[geometry-capture] harmony.Patch() FAILED: " + FullError(he) + "  " + detail);
                    return false;
                }
                catch (Exception patchEx)
                {
                    ProbeMod.Log("[geometry-capture] harmony.Patch() FAILED: " + FullError(patchEx));
                    return false;
                }
                ProbeMod.Log("[geometry-capture] patched " + partType.FullName + ".InitializePart()");
                return true;
            }
            catch (Exception e)
            {
                ProbeMod.Log("[geometry-capture] Apply() failed: " + FullError(e));
                return false;
            }
        }

        // Walks the FULL exception chain (type name + message per level, incl.
        // InnerException and, for AggregateException-style cases, any nested
        // chain) -- Harmony/MonoMod failures are frequently a generic outer
        // exception wrapping the REAL cause one or more levels down, and a
        // bare e.Message alone (as used everywhere else in this file) throws
        // that away. Used only for this one Harmony-patching path since it's
        // the one place a vague top-level message has already proven useless
        // ("IL Compile Error (unknown location)", 2026-08-27).
        static string FullError(Exception e)
        {
            var sb = new StringBuilder();
            int depth = 0;
            while (e != null && depth < 6)
            {
                if (depth > 0) sb.Append(" ---> ");
                sb.Append(e.GetType().FullName).Append(": ").Append(e.Message);
                e = e.InnerException;
                depth++;
            }
            return sb.ToString();
        }

        // __instance declared as `object` deliberately -- this file never
        // references the real Part type at compile time, and Harmony passes
        // the live instance through regardless of the postfix's declared
        // parameter type.
        static void Postfix(object __instance)
        {
            GeometryCapture.OnPartInitialized(__instance);
        }

        static Type FindPartType()
        {
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type t = null;
                try { t = a.GetType("SFS.Parts.Part", false); } catch { }
                if (t != null) return t;
            }
            return null;
        }
    }
}
