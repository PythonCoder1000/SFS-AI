using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
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
        public override string ModNameID => "sfs_probe";
        public override string DisplayName => "SFS Probe (remote)";
        public override string Author => "christian";
        public override string MinimumGameVersionNecessary => "1.6.00.00";
        public override string ModVersion => "0.24.0";
        public override string Description => "Remote-controlled data probe. Poll command.txt.";

        public static string OutDir;

        public override void Load()
        {
            OutDir = ModFolder;
            Log("=== v0.24 loaded (achievements command: reads SFS.Logs.Challenge catalog + per-rocket completion) ===");
            SceneManager.sceneLoaded += OnSceneLoaded;
            Probe.DumpMenu("load");
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

        public static void StartRecording()
        {
            if (Telemetry) return;
            flightNumber++;
            sampleCount = 0;
            lastRocketCount = -1;   // fresh baseline each flight -- avoids a false
                                    // separation trigger from leftover debris or
                                    // the previous recording's rocket count
            ArchiveTelemetry();
            Telemetry = true;
            ProbeMod.Result("[hotkey] recording STARTED  flight #" + flightNumber);
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
                                    "  fixedDelta=" + Time.fixedDeltaTime.ToString("R"));
                    break;

                case "snapshot": DumpFlight("cmd"); break;
                case "world":    WroteWorld = false; DumpWorld("cmd"); break;
                case "menu":     DumpMenu("cmd"); break;

                case "telemetry":
                    if (arg == "on") StartRecording(); else StopRecording();
                    break;

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

                case "cheat":
                {
                    object ss = FindComponent("SFS.World.SandboxSettings");
                    Invoke(ss, "Toggle" + arg, new object[0]);
                    ProbeMod.Result("toggled " + arg);
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
                object rb = Get(r, "rb2d");
                object throttle = Get(r, "throttle");
                object arrowkeys = Get(r, "arrowkeys");
                double t = ToD(Get(loc, "time"));
                float fdt = Time.fixedDeltaTime;
                float thr = ToF(GetWrapped(throttle, "throttlePercent"));
                bool thrOn = ToB(GetWrapped(throttle, "throttleOn"));
                float turnAxis = ToF(GetWrapped(arrowkeys, "turnAxis"));
                float mass = ToF(Get(rb, "mass"));
                float torque = SumEnabledTorque(r);
                bool rcsOn = ToB(GetWrapped(arrowkeys, "rcs"));
                int rcsFiring = CountFiringThrusters(r);
                object eng = GetEngineDirection(r);   // (dirX, dirY, gimbalOn) of first active engine, local space

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
                if (eng != null)
                {
                    var t4 = (Tuple<float,float,bool,float>)eng;
                    si.Append(",\"thrustDirX\":").Append(Num(t4.Item1));
                    si.Append(",\"thrustDirY\":").Append(Num(t4.Item2));
                    si.Append(",\"gimbalOn\":").Append(t4.Item3 ? "true" : "false");
                    si.Append(",\"throttleOut\":").Append(Num(t4.Item4));
                }
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
                object planet = Unwrap(Get(loc, "planet"));
                st.Append(",\"body\":\"").Append(Get(planet, "codeName")).Append("\"");
                st.Append("}");
                ProbeMod.Append("truth.jsonl", st.ToString());

                sampleCount++;
            }
            catch (Exception e) { ProbeMod.Log("sample error: " + e.Message); }
        }

        // Part.temperature is a plain public float, no wrapper. Part count
        // dropping between ticks is the cleanest available destruction signal
        // -- cheaper and more certain than trying to infer breakup from a
        // temperature threshold we've never independently confirmed.
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
                    float temp = ToF(Get(part, "temperature"));
                    if (temp > maxTemp) maxTemp = temp;
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
        static IEnumerable<object> ModuleValues(object part)
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

        // Resolves LOCAL (part-space) thrust direction AND the resolved output
        // throttle of the first active, enabled EngineModule. thrustNormal is the
        // game's own Composed_Float, already gimbal-deflected. throttle_Out is
        // the value AFTER RecalculateEngineThrottle gates it by engineOn -- the
        // actual force multiplier, distinct from the rocket's commanded 'thr'
        // (master throttlePercent), which this engine might not be honoring if
        // its own engineOn flag differs from the master state.
        static Tuple<float,float,bool,float> GetEngineDirection(object rocket)
        {
            try
            {
                object holder = Get(rocket, "partHolder");
                object parts = Get(holder, "parts");
                var en = parts as System.Collections.IEnumerable;
                if (en == null) return null;
                foreach (object part in en)
                {
                    foreach (object mv in ModuleValues(part))
                    {
                        if (mv.GetType().Name != "EngineModule") continue;
                        bool engineOn = ToB(GetWrapped2(Get(mv, "engineOn")));
                        if (!engineOn) continue;
                        object normal = Get(mv, "thrustNormal");
                        object nx = Get(normal, "x");
                        object ny = Get(normal, "y");
                        float dx = ToF(GetWrapped2(nx));
                        float dy = ToF(GetWrapped2(ny));
                        bool gimbal = ToB(GetWrapped2(Get(mv, "gimbalOn")));
                        float throttleOut = ToF(GetWrapped2(Get(mv, "throttle_Out")));
                        return Tuple.Create(dx, dy, gimbal, throttleOut);
                    }
                }
            }
            catch { }
            return null;
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
        static bool ToB(object o) { return (o is bool) && (bool)o; }

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

        static object Get(object o, string member)
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
}
