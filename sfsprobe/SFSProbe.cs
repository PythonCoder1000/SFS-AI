using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
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
        public const string VersionString = "0.36.0";

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
            Log("=== v" + VersionString + " loaded (new aeroformula command: reads the 4 live AeroFormula coefficients velPow/densityPow/tempOffset/m off GameManager.main.aeroData, needed to close the heat-formula validation gap; GetHeatState fixed to read via HeatModule/Part's Temperature property instead of the always-wrong Part.temperature field, and to exclude +-Inf sentinels; geometry capture below is the abandoned Harmony path, kept for reference) ===");
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
            if (Probe.AutoStop) Probe.CheckAutoStop();
            if (Probe.Telemetry) Probe.CheckSeparation();
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
        static int sampleCount;
        static int flightNumber;

        // Scoped-telemetry field spec (v0.29). null = default full-schema
        // recording (unchanged behavior). Non-null = only these fields are
        // sampled each tick, written to truth.jsonl alone (inputs.jsonl is
        // skipped entirely in this mode). Each entry is either a dotted
        // reflection path (e.g. "rb2d.mass", "location.velocity.x") walked
        // via ResolvePath, or "computed:NAME" for a registered multi-field
        // helper (e.g. "computed:dragArea") dispatched via AppendComputedField.
        // See Command()'s "telemetry" case for the command syntax.
        static string[] telemetryFields;

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

        public static void OnScene(string n) { WroteWorld = false; DumpWorld("scene:" + n); }

        // ---------- hotkey recording ----------

        public static void StartRecording(string[] fields = null)
        {
            if (Telemetry) return;
            flightNumber++;
            sampleCount = 0;
            lastRocketCount = -1;   // fresh baseline each flight -- avoids a false
                                    // separation trigger from leftover debris or
                                    // the previous recording's rocket count
            telemetryFields = fields;
            ArchiveTelemetry();
            Telemetry = true;
            string scopeNote = fields == null ? "full" : ("scoped[" + fields.Length + "]: " + string.Join(",", fields));
            ProbeMod.Result("[hotkey] recording STARTED  flight #" + flightNumber + "  mode=" + scopeNote);
        }

        public static void StopRecording()
        {
            if (!Telemetry) return;
            Telemetry = false;
            string a1 = ArchiveOne("inputs.jsonl", "inputs", flightNumber);
            string a2 = ArchiveOne("truth.jsonl", "truth", flightNumber);
            ProbeMod.Result("[hotkey] recording STOPPED  flight #" + flightNumber +
                             "  samples=" + sampleCount +
                             "  -> " + (a1 ?? "(no inputs)") + "  " + (a2 ?? "(no truth)"));
            telemetryFields = null;   // next hotkey (Enter) always starts back in full mode
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
                    string[] parts3 = line.Split(new char[] { ' ' }, 3);
                    string mode = parts3.Length > 1 ? parts3[1] : null;
                    if (mode == "on")
                    {
                        string[] fields = null;
                        if (parts3.Length > 2 && !string.IsNullOrWhiteSpace(parts3[2]))
                            fields = parts3[2].Split(',');
                        StartRecording(fields);
                    }
                    else
                    {
                        StopRecording();
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
                    // file (truth.jsonl), one JSON key per requested field. See
                    // ResolvePath/AppendComputedField below and the "telemetry"
                    // command case above for the spec syntax. inputs.jsonl is
                    // deliberately NOT written in this mode.
                    var sb3 = new StringBuilder();
                    sb3.Append("{\"t\":").Append(Num(t));
                    foreach (string rawField in telemetryFields)
                    {
                        string f = rawField.Trim();
                        if (f.Length == 0) continue;
                        if (f.StartsWith("computed:"))
                        {
                            string name = f.Substring("computed:".Length);
                            if (!AppendComputedField(name, r, sb3))
                                sb3.Append(",\"").Append(name).Append("Error\":\"unknown computed field\"");
                        }
                        else
                        {
                            object val = ResolvePath(r, f);
                            sb3.Append(",\"").Append(f).Append("\":").Append(Num(val));
                        }
                    }
                    sb3.Append("}");
                    ProbeMod.Append("truth.jsonl", sb3.ToString());
                    sampleCount++;
                    return;
                }

                object rb = Get(r, "rb2d");
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
                object eng = GetEngineArray(r);   // one entry per engine/booster module, on or off

                // ---- inputs.jsonl ----
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
                si.Append(",\"engines\":[").Append(string.Join(",", ((List<string>)eng).ToArray())).Append("]");
                si.Append("}");
                ProbeMod.Append("inputs.jsonl", si.ToString());

                // ---- truth.jsonl ----
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
                object planet = Unwrap(Get(loc, "planet"));
                st.Append(",\"body\":\"").Append(Get(planet, "codeName")).Append("\"");
                st.Append("}");
                ProbeMod.Append("truth.jsonl", st.ToString());

                sampleCount++;
            }
            catch (Exception e) { ProbeMod.Log("sample error: " + e.Message); }
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
            Type t = w.GetType();
            var p = t.GetProperty("Value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (p != null) { try { return p.GetValue(w, null); } catch { } }
            var f = t.GetField("value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (f != null) { try { return f.GetValue(w); } catch { } }
            return w;
        }

        // ---------- archiving ----------

        static void ArchiveTelemetry()
        {
            ArchiveOne("inputs.jsonl", "inputs", 0);
            ArchiveOne("truth.jsonl", "truth", 0);
        }

        static string ArchiveOne(string liveName, string tag, int flightNum)
        {
            try
            {
                string live = Path.Combine(ProbeMod.OutDir ?? ".", liveName);
                if (!File.Exists(live)) return null;
                if (new FileInfo(live).Length == 0) { File.Delete(live); return null; }

                string archiveDir = Path.Combine(ProbeMod.OutDir ?? ".", "archive");
                Directory.CreateDirectory(archiveDir);
                string stamp = DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss");
                string name = flightNum > 0
                    ? "flight" + flightNum.ToString("D2") + "_" + tag + "_" + stamp + ".jsonl"
                    : tag + "_" + stamp + ".jsonl";
                string dest = Path.Combine(archiveDir, name);
                File.Move(live, dest);
                ProbeMod.Log("archived -> archive/" + name);
                return "archive/" + name;
            }
            catch (Exception e) { ProbeMod.Log("archive failed (" + liveName + "): " + e.Message); return null; }
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
            Type t = w.GetType();
            var p = t.GetProperty("Value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (p != null && p.CanWrite)
            {
                try { p.SetValue(w, Convert.ChangeType(val, p.PropertyType), null); return true; } catch { }
            }
            var f = t.GetField("value", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
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
            drag = 0f; copX = 0f; copY = 0f; allCount = 0; exposedCount = 0;
            try
            {
                object aero = Get(rocket, "aero");
                if (aero == null) return false;

                Type matrixType = FindType("Matrix2x2");
                Type aeroModuleType = FindType("SFS.World.Drag.AeroModule");
                if (matrixType == null || aeroModuleType == null) return false;

                object dloc = Unwrap(Get(rocket, "location"));
                object velocity = GetWrapped(dloc, "velocity");
                double velocityAngle = ToD(Get(velocity, "AngleRadians"));
                float rotationInput = (float)(-(velocityAngle - Math.PI / 2.0));
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
