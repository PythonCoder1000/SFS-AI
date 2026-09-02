"""
forward_sim.py -- forward-integrates the CONFIRMED physics formulas
starting from a real telemetry sample, for a given duration. Built
2026-08-29; extended 2026-09-02 (multiple sessions same day) first to
replace the frozen-dragArea coast-only simplification with a rotating-
state model (dragArea(AoA), aero torque, SAS), then to integrate every
remaining "Bucket A" item from bookkeeping/active_state.md's physics
status list: thrust, fuel burn, gimbal, RCS (force + torque), parachute
drag, staging separation, heat accumulation, and terrain collision.

RK4 integration for the CONTINUOUS state (position, velocity, mass,
theta, omega, heat) -- accurate enough at a moderate timestep (default
dt=0.25s) to predict minutes ahead without matching the real telemetry's
60Hz sampling rate. SAS, gimbal, RCS, staging, and terrain are DISCRETE
mechanisms (deadbeat clamp, rate-limited MoveTowards, on/off gate,
one-time event, one-time event respectively) and are applied as
post-step corrections after each RK4 outer step, not blended into the
continuous derivative -- this is a deliberate operator-splitting choice,
consistent with how SAS was already handled before this integration
pass, not a shortcut invented to avoid the harder cases.

--------------------------------------------------------------------
THIS IS AN INTEGRATION-ONLY PASS (2026-09-02) -- read before trusting
any of the new numbers
--------------------------------------------------------------------
Everything below marked NEW was added to make code exist and run
without crashing when combined with the rest of the module (isolation
flags let each piece be tested independently once real flight data is
available). NONE of it has been validated against a real flight in this
pass -- that is explicitly out of scope for this session per the task
this was written under. Existing items (drag/AoA, aero torque, SAS) that
WERE validated in earlier sessions keep their validation notes below;
new items do not have equivalent claims and should not be read as
having any.

--------------------------------------------------------------------
STATE MODEL
--------------------------------------------------------------------
Continuous (RK4-integrated) state, in order:
    px, py, vx, vy   -- position/velocity, world/orbital frame (m, m/s)
    m                -- mass (t) -- NEW: now a real integrated state,
                        was frozen at the starting sample's value before
                        this pass. Decreases via engine + RCS fuel flow
                        (section 1.3/2.2's confirmed formula) whenever
                        flags["fuel_burn"] is True.
    theta            -- orientation (deg), rb2d.rotation convention
    omega            -- angular velocity (deg/s), rb2d.angularVelocity
    heat_temp        -- NEW: a single representative "hottest part"
                        temperature (deg C), integrated via the
                        CONFIRMED, LIVE-VALIDATED (0.18% mean peak
                        error, sfs_telemetry.py's
                        validate_heat_accumulation) HeatManager.
                        ApplyHeat/DissipateHeat accumulation. This is a
                        SIMPLIFICATION: the real game tracks temperature
                        PER PART, each with its own exposed-surface
                        fraction; this module tracks exactly one
                        representative value (caller supplies the
                        exposed_surface_for_heat to use, e.g. the most
                        heat-exposed part on the craft). Full per-part
                        tracking would need a list of parts each with
                        their own exposed-surface state -- not
                        implemented, flagged as a real scope limit, not
                        silently approximated as "close enough".

Discrete (post-step) state:
    gimbal_times     -- NEW: one per engine with has_gimbal=True, the
                        MoveModule.time value (confirmed range -1..1 on
                        the one real engine read live, B1.10), chasing a
                        target derived from the SAME turnAxis_Input ==
                        output_TurnAxisTorque signal SAS uses (also
                        confirmed live, B1.10, 0.0000% error). Updated
                        via rate-limited MoveTowards, not a smooth ODE.

craft_config (static, caller-supplied -- this offline module has no way
to read a specific craft's real part layout, so none of this is
fabricated, it's an explicit required input):
    engines: [{thrust_ton, isp, throttle (0-1, held CONSTANT for the
               whole sim -- no throttle-profile modeling), scale (default
               1.0, section 1.3's fourth fuel-flow term for a scaled
               part), position_local (x,y offset from CoM, body-fixed
               frame, meters), base_direction_local (x,y unit vector,
               body-fixed frame, gimbal=0 direction), has_gimbal (bool),
               gimbal_range_deg, gimbal_animation_time_s,
               rotation_direction (+-1, RotationDirection(transform)'s
               sign flip, B1.10 -- not derivable, must be supplied)}, ...]
    rcs_modules: [{thrust_ton, isp, thruster_count, sum_normal_local
                   (x,y, body-fixed frame, PER-MODULE scoped -- section
                   5.3's confirmed per-module, not pooled, scoping),
                   position_local (x,y offset from CoM, body-fixed)}, ...]
    parachutes: [{position_local (x,y offset from CoM, body-fixed),
                  drag_curve: [(state, value), ...] control points,
                  LINEARLY interpolated (see _interp_curve -- a
                  documented simplification; the real AnimationCurve is
                  a Hermite spline and no real chute's keyframes have
                  been read live the way the one gimbal curve was),
                  deployed_state (float, held CONSTANT for the whole
                  sim -- deployment ANIMATION itself, i.e. how `state`
                  itself transitions over time, is not modeled here;
                  not IL-confirmed in what this session read)}, ...]
    isp_multiplier: 1.0 (Normal difficulty, confirmed; override for
                    Hard/Realistic per section 1.3's ispMultipliers
                    table [1.0, 1.0, 1.5])
    exposed_surface_for_heat: float, the single representative part's
                    ExposedSurface value for the heat model above
    dry_mass_t: Optional[float] -- mass floor once fuel is exhausted
                    (this module has no real tank-capacity tracking, so
                    without this, mass would integrate toward zero and
                    beyond; supply the craft's real dry mass to avoid
                    an unphysical negative-mass state)
    heat_tolerance_c: float, default 412.0 (confirmed default:
                    HeatTolerance.Low=400 * 1.03 destroy multiplier,
                    section 5.1) -- used only to report a
                    "would_destroy" flag on output points, does not
                    stop the integration (a real craft loses a PART, not
                    necessarily control -- destruction handling beyond
                    that single flag is out of scope)

staging_events: Optional[list[{"t": float (sim-relative seconds),
    "ejected_mass": float, "eject_delta_v_local": Optional[(dx,dy)]}]].
    Momentum conservation (section 2.7, confirmed) determines the
    CONTINUING craft's velocity change from the ejected piece's delta-v
    via mass ratio -- but this module has no real separationForce read
    for any specific craft (it's a parametric expression, section 2.7's
    addition), so eject_delta_v_local defaults to None (zero -- pure
    mass drop, no velocity kick) unless supplied. Angular velocity is
    confirmed to carry over unchanged to both pieces (section 2.7) --
    theta/omega are NOT touched by a staging event here, matching that.

terrain_lookup: Optional[Callable[[float], float]] -- angle_deg (from
    +x axis, atan2 convention, matching everything else in this module)
    -> terrain height (m) above the datum radius, e.g. from a live
    Planet.GetTerrainHeightAtAngle probe read (section 5.4, confirmed).
    If None, falls back to a flat datum (height=0) floor -- conservative
    for anywhere with real terrain above datum (mountains), wrong the
    other way for anywhere below it (ocean basins, if this body has an
    ocean) -- documented, not silently assumed accurate.
--------------------------------------------------------------------
"""

import json
import math
import sys
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).parent))
from aoa_dragarea import lookup_field  # noqa: E402 (path setup above)

PLANET_CONSTANTS = {
    "Earth": {
        "radius_m": 314970.0,
        "mu": 972219788820.0,
        "atmosphere_height_m": 30000.0,
        "rho0": 0.005,
        "curve": 10.0,
    },
}

RAD2DEG = 57.29578

# Isolation flags. Each defaults to True (matches prior behavior exactly
# when combined with supplying the relevant data). Explicitly setting
# one False disables that component's CONTRIBUTION even if its required
# data is present -- "I have the data but want this off for a test" is
# different from "I don't have the data" (component-specific None checks
# below), and both work independently. NEW flags (2026-09-02 Bucket-A
# pass): thrust, fuel_burn, gimbal, rcs, parachute_drag, heat, terrain,
# staging.
DEFAULT_FLAGS = {
    "gravity": True, "drag": True, "aero_torque": True, "sas": True,
    "thrust": True, "fuel_burn": True, "gimbal": True, "rcs": True,
    "parachute_drag": True, "heat": True, "terrain": True, "staging": True,
}


def _resolve_flags(flags: Optional[dict]) -> dict:
    resolved = dict(DEFAULT_FLAGS)
    if flags:
        unknown = set(flags) - set(DEFAULT_FLAGS)
        if unknown:
            raise ValueError(f"unknown physics flag(s): {sorted(unknown)}; "
                              f"valid flags are {sorted(DEFAULT_FLAGS)}")
        resolved.update(flags)
    return resolved


def atmospheric_density(h: float, body: dict) -> float:
    """Verbatim copy of sfs_telemetry.py's confirmed formula."""
    H = body["atmosphere_height_m"]
    if h < 0 or h > H:
        return 0.0
    curve = body["curve"]
    return (math.exp(-curve * h / H) - math.exp(-curve)) * body["rho0"]


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def _rotate_body_vector(x: float, y: float, theta_deg: float) -> tuple[float, float]:
    """Rotates a body-fixed local-frame 2D vector by the craft's current
    orientation theta_deg. Uses the standard Unity CCW-positive
    convention (matches how omega/theta already accumulate via plain
    addition elsewhere in this module, and Unity's default
    Transform.eulerAngles.z / Rigidbody2D.rotation behavior).

    CAVEAT: this specific convention (CCW-positive rotating a body-fixed
    part position/direction) has NOT been independently IL-confirmed in
    this project the way e.g. the AoA heading offset was -- it's the
    standard Unity default, used here because no project-specific
    evidence contradicts it, not because it's been directly verified for
    arbitrary body-fixed part positions. Flagged in the integration
    report, not silently assumed solid."""
    a = math.radians(theta_deg)
    ca, sa = math.cos(a), math.sin(a)
    return (x * ca - y * sa, x * sa + y * ca)


def _interp_curve(curve_points: list, x: float) -> float:
    """Linear interpolation between (state, value) control points,
    sorted by state. NOT a Hermite spline (Unity's real AnimationCurve)
    -- documented simplification (see module docstring's parachutes
    section). Empty input -> 0.0 (no contribution, fails safe)."""
    if not curve_points:
        return 0.0
    pts = sorted(curve_points, key=lambda p: p[0])
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            frac = (x - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)
    return pts[-1][1]  # unreachable in practice


def compute_turn_axis(omega: float, mass: float, torque_effective: Optional[float],
                       dt: float) -> float:
    """The SAS deadbeat law's turnAxis (sfs_source_reference.md B1.3),
    extracted out of apply_sas() so gimbal -- confirmed to read the
    IDENTICAL turnAxis_Input == output_TurnAxisTorque signal,
    sfs_source_reference.md B1.10, 0.0000% error live -- can reuse it
    instead of duplicating (and risking desyncing from) the same law.
    Returns 0.0 (no correction) for any degenerate input rather than
    raising: dt<=0, mass<=0, or torque_effective is None (no SAS data
    supplied for this craft)."""
    if dt <= 0 or mass <= 0 or torque_effective is None:
        return 0.0
    delta = torque_effective * RAD2DEG / mass * dt
    if delta == 0:
        return 0.0
    return max(-1.0, min(1.0, omega / delta))


def apply_sas(omega: float, mass: float, torque_effective: float, dt: float) -> float:
    """Discrete deadbeat SAS correction (sfs_source_reference.md B1.3 +
    ApplyTorque, confirmed). See module docstring for the operator-
    splitting rationale (applied once per RK4 outer step, proven exact
    for the pure-SAS mechanism -- see python_changelog.md's 2026-09-02
    SAS entry for the telescoping proof, trimmed here to keep this
    docstring from growing without bound across sessions)."""
    turn_axis = compute_turn_axis(omega, mass, torque_effective, dt)
    if turn_axis == 0.0:
        return omega
    return omega - torque_effective * RAD2DEG / mass * turn_axis * dt


def air_temperature(v: float, v_radial: float, density: float,
                     body_name: str = "Earth", difficulty: str = "Normal") -> float:
    """AeroFormula.GetTemperature, confirmed 2026-08-30 (LIVE-VALIDATED,
    median 0.0000% error, sfs_telemetry.py's predicted_reentry_temperature
    -- ported inline here, verbatim, so forward_sim.py doesn't need
    sfs_telemetry.py as an import dependency; NOT reimplemented from the
    formula text, copied from the already-validated version to avoid
    re-risking the additive-vs-multiplicative bug already found and
    fixed once in this project).

    v: speed magnitude (m/s). v_radial: SIGNED component of velocity
    along the position vector (positive = moving away from the planet,
    i.e. ascending) -- NOT simply vy; the caller must compute
    (vx*px+vy*py)/r, since this module's world frame is planet-centered
    Cartesian, not a "vertical = +y" frame."""
    coef = {"velPow": 1.85, "densityPow": 2.2, "tempOffset": -500.0, "m": 1.47}
    atmo = {"Earth": {"minHeatingVelocityMultiplier": 1.0}}.get(body_name)
    if atmo is None:
        return 0.0  # no confirmed atmospherePhysics for this body -- fail safe, not fabricated
    hvm = {"Normal": 1.0, "Hard": 1.3, "Realistic": 4.5}[difficulty]
    mhvm = {"Normal": 1.0, "Hard": 1.3, "Realistic": 3.0}[difficulty]
    min_heat_velocity = atmo["minHeatingVelocityMultiplier"] * mhvm * 250.0

    vv = v / hvm
    vvy = v_radial / hvm
    min_hv = min_heat_velocity / hvm
    if vvy > 0.0:
        vv -= min(vvy * 2.5, vv * 0.5)
    if vv < 0 or density <= 0:
        return 0.0

    t = (vv ** coef["velPow"]) * (density ** (1.0 / coef["densityPow"])) / coef["m"]
    ascent_term = min(vvy / vv * 2.0, 0.4) if (vvy > 0.0 and vv > 0) else 0.0
    t += coef["tempOffset"] * (ascent_term + 0.2)

    cap = (vv - min_hv) * 6.0
    if t > cap:
        t = cap
    if t > 2000.0:
        t = 2000.0 + (t - 2000.0) / 1.5
    return t if t > 0.0 else 0.0


def _heat_derivative(heat_temp: float, air_temp: float, exposed_surface: float) -> float:
    """d(heat_temp)/dt, from the CONFIRMED, LIVE-VALIDATED (0.18% mean
    peak error) HeatManager.ApplyHeat/DissipateHeat rates, expressed as
    a continuous derivative (the original is a per-tick discrete
    update; treated here as a first-order relaxation ODE, valid since
    absorb/dissipate rates don't themselves depend on dt -- unlike
    SAS/gimbal's genuinely rate-LIMITED, target-clamping mechanisms,
    this one integrates cleanly under RK4)."""
    exposed = max(0.0, exposed_surface)
    delta = air_temp - heat_temp
    if delta > 0:
        surface_factor = 1 + math.log10(exposed + 1)
        d = delta if delta < 1000 else (delta * delta / 1000)
        return surface_factor * d * 0.02
    return -(10.0 + heat_temp * 0.01)


def _aero_force_and_cop(theta_deg: float, vx: float, vy: float, omega: float, h: float,
                         aoa_table: Optional[dict], com_local: Optional[tuple],
                         parachutes: Optional[list], body: dict,
                         enable_drag: bool, enable_parachute: bool
                         ) -> tuple[float, float, Optional[float], Optional[float], float]:
    """Base drag (section 2.3) + parachute blending (section 2.8),
    confirmed formulas, combined into ONE implementation shared by both
    the translational (accel) and rotational (torque) callers -- avoids
    the drag/parachute logic being duplicated (and risking desyncing)
    across two places the way it would if each caller reimplemented it.

    Returns (force_x, force_y, cop_applied_x, cop_applied_y, drag_area).
    cop_applied_* is None if com_local wasn't supplied (translation
    doesn't need it; only torque does) or if velocity is ~zero.
    """
    if aoa_table is None or not enable_drag:
        cx, cy = (com_local if com_local else (None, None))
        return 0.0, 0.0, cx, cy, 0.0
    v = math.hypot(vx, vy)
    if v < 1e-9:
        cx, cy = (com_local if com_local else (None, None))
        return 0.0, 0.0, cx, cy, 0.0

    heading_rad = math.atan2(vy, vx)
    aoa_deg = _wrap180((theta_deg + 90.0) - math.degrees(heading_rad))
    drag_area = lookup_field(aoa_table, aoa_deg, "dragArea")
    if drag_area is None:
        drag_area = 0.0

    density = atmospheric_density(h, body)

    # Pre-density scalar "force", matching section 2.8's confirmed
    # pseudocode exactly (force = dragArea*1.5*speedSq, BEFORE density
    # and BEFORE direction -- density/direction applied once at the end,
    # after any parachute blending).
    pre_density_force = drag_area * 1.5 * v * v

    cop_x = cop_y = None
    if com_local is not None:
        comx, comy = com_local
        cop_x_vel = lookup_field(aoa_table, aoa_deg, "dragCopX")
        cop_y_vel = lookup_field(aoa_table, aoa_deg, "dragCopY")
        if cop_x_vel is not None and cop_y_vel is not None:
            a = heading_rad - math.pi / 2
            ca, sa = math.cos(a), math.sin(a)
            cop_world_x = ca * cop_x_vel - sa * cop_y_vel
            cop_world_y = sa * cop_x_vel + ca * cop_y_vel
            cop_x = comx + (cop_world_x - comx) * 0.2
            cop_y = comy + (cop_world_y - comy) * 0.2
        else:
            cop_x, cop_y = comx, comy

    # Parachute blending (section 2.8) -- sequential compounding, each
    # chute's weighted-average cop blend uses the ALREADY-updated force
    # from the previous chute, not the original pre-parachute value.
    if enable_parachute and parachutes and com_local is not None and cop_x is not None:
        omega_rad = math.radians(omega)
        comx, comy = com_local
        for chute in parachutes:
            deployed_state = chute.get("deployed_state", 0.0)
            if deployed_state <= 0:
                continue  # 0 = stowed, no contribution (matches targetState gate)
            pos_local = chute.get("position_local", (0.0, 0.0))
            rx, ry = _rotate_body_vector(pos_local[0], pos_local[1], theta_deg)
            chute_world_x, chute_world_y = comx + rx, comy + ry
            # GetPointVelocity: bulk velocity + omega x r (2D perpendicular,
            # the one place in the whole confirmed aero chain that is
            # rotation-aware -- section 2.8's confirmation).
            chute_vx = vx + omega_rad * (-ry)
            chute_vy = vy + omega_rad * rx
            chute_speed_sq = chute_vx * chute_vx + chute_vy * chute_vy
            curve_val = _interp_curve(chute.get("drag_curve", []), deployed_state)
            chute_drag = chute_speed_sq * curve_val
            if chute_drag <= 0:
                continue
            new_force = pre_density_force + chute_drag
            if new_force > 1e-12:
                cop_x = (cop_x * pre_density_force + chute_world_x * chute_drag) / new_force
                cop_y = (cop_y * pre_density_force + chute_world_y * chute_drag) / new_force
            pre_density_force = new_force

    force_mag = pre_density_force * density
    if force_mag <= 0 or v < 1e-9:
        return 0.0, 0.0, cop_x, cop_y, drag_area
    force_x = -(vx / v) * force_mag
    force_y = -(vy / v) * force_mag
    return force_x, force_y, cop_x, cop_y, drag_area


def _engine_thrust(theta_deg: float, engines: Optional[list], gimbal_times: list,
                    isp_multiplier: float, enable_thrust: bool, enable_fuel_burn: bool
                    ) -> tuple[float, float, float, list]:
    """Section 2.2 (thrust) + section 5.2 (confirmed: N independent
    forces, NOT a resultant -- 'there is no summation model, because
    there is no summation') + section 1.3 (fuel-flow rate, including the
    'scale' term a reimplementation needs for a scaled part).

    Returns (fx_world, fy_world, mass_flow_rate [positive = mass LOST
    per second], per_engine_levers) where per_engine_levers is a list of
    (lever_x, lever_y, force_x, force_y) tuples, lever_* already CoM-
    relative (position_local rotated by theta_deg -- engines'
    position_local is defined AS a CoM-relative offset, see module
    docstring), for the caller to fold into a torque sum if inertia is
    available.
    """
    fx_total = fy_total = 0.0
    mass_flow = 0.0
    per_engine: list = []
    if not engines:
        return 0.0, 0.0, 0.0, per_engine

    for idx, eng in enumerate(engines):
        throttle = eng.get("throttle", 0.0)
        if throttle <= 0:
            continue
        thrust_ton = eng.get("thrust_ton", 0.0)
        isp = eng.get("isp", 0.0)
        pos_local = eng.get("position_local", (0.0, 0.0))
        base_dir = eng.get("base_direction_local", (0.0, 1.0))

        gimbal_deg = 0.0
        if eng.get("has_gimbal"):
            gimbal_time = gimbal_times[idx] if idx < len(gimbal_times) else 0.0
            gimbal_range = eng.get("gimbal_range_deg", 0.0)
            # time ranges -1..1 over +/-gimbal_range_deg -- confirmed live
            # shape (B1.10): linear, tangents == chord slope.
            gimbal_deg = gimbal_time * gimbal_range

        gr = math.radians(gimbal_deg)
        cg, sg = math.cos(gr), math.sin(gr)
        dx = base_dir[0] * cg - base_dir[1] * sg
        dy = base_dir[0] * sg + base_dir[1] * cg
        world_dx, world_dy = _rotate_body_vector(dx, dy, theta_deg)

        if enable_thrust:
            f_mag = thrust_ton * 9.8 * throttle  # section 2.2
            fx, fy = world_dx * f_mag, world_dy * f_mag
            fx_total += fx
            fy_total += fy
            lever_x, lever_y = _rotate_body_vector(pos_local[0], pos_local[1], theta_deg)
            per_engine.append((lever_x, lever_y, fx, fy))

        if enable_fuel_burn and isp > 0:
            scale = eng.get("scale", 1.0)
            mass_flow += thrust_ton * scale * throttle / (isp * isp_multiplier)

    return fx_total, fy_total, mass_flow, per_engine


def _rcs_force(theta_deg: float, turn_axis: float, omega: float,
               rcs_modules: Optional[list], enable_rcs: bool
               ) -> tuple[float, float, list]:
    """Section 5.3, confirmed-live: RcsModule.TorqueThrust's gate
    (|TurnAxis| >= 0.95 OR |angularVelocity| >= 2 deg/s) is checked using
    `turn_axis`, the SAME SAS-computed value gimbal reads -- NOT just
    |omega| alone (an earlier draft of this integration used |omega|
    only and would have MISSED the common case where SAS saturates at
    turn_axis=+-1 well before omega reaches 2 deg/s on a weak-torque
    craft, since turn_axis saturates once |omega| exceeds just ONE
    tick's SAS authority, which can be well under 2 deg/s -- caught
    while writing this, not left in).

    Force is per-module, on/off, NOT proportional to anything when
    firing (confirmed). sumNormal/count/position are PER MODULE
    (confirmed live, D3.8 -- pooling would overstate force ~6x, a
    mistake already caught once in this project's own hand-derivation).

    Returns (fx_world, fy_world, per_module_levers) -- mass flow and
    torque are the caller's job (this only computes the force+geometry,
    kept separate so the caller can apply this as the discrete post-step
    correction the module docstring describes, consistent with SAS/
    gimbal's treatment)."""
    fx_total = fy_total = 0.0
    per_module: list = []
    if not enable_rcs or not rcs_modules:
        return 0.0, 0.0, per_module
    if abs(turn_axis) < 0.95 and abs(omega) < 2.0:
        return 0.0, 0.0, per_module  # gate closed, matches TorqueThrust exactly

    for mod in rcs_modules:
        thrust_ton = mod.get("thrust_ton", 0.0)
        count = mod.get("thruster_count", 0)
        if count <= 0 or thrust_ton <= 0:
            continue
        sum_normal_local = mod.get("sum_normal_local", (0.0, 0.0))
        pos_local = mod.get("position_local", (0.0, 0.0))
        world_nx, world_ny = _rotate_body_vector(sum_normal_local[0], sum_normal_local[1], theta_deg)
        f_mag = thrust_ton * count * 9.8
        fx, fy = world_nx * f_mag, world_ny * f_mag
        fx_total += fx
        fy_total += fy
        lever_x, lever_y = _rotate_body_vector(pos_local[0], pos_local[1], theta_deg)
        per_module.append((lever_x, lever_y, fx, fy, thrust_ton, count, mod.get("isp", 0.0)))

    return fx_total, fy_total, per_module


def _update_gimbal_time(gimbal_time: float, target: float,
                         animation_time_s: Optional[float], dt: float) -> float:
    """MoveModule.Update, confirmed B1.10: linear MoveTowards, NOT eased.
    animation_time_s<=0 or None matches the IL's speed=10000 case --
    effectively instant (reaches target within one step)."""
    if animation_time_s is None or animation_time_s <= 0:
        return target
    speed = dt / animation_time_s
    if gimbal_time < target:
        return min(gimbal_time + speed, target)
    elif gimbal_time > target:
        return max(gimbal_time - speed, target)
    return gimbal_time


# ---------------------------------------------------------------------
# Continuous state: (px, py, vx, vy, m, theta, omega, heat_temp)
# ---------------------------------------------------------------------

_STATE_LEN = 8


def _derivative(state: tuple, body: dict, aoa_table: Optional[dict],
                 com_local: Optional[tuple], inertia: Optional[float],
                 craft_config: Optional[dict], gimbal_times: list, flags: dict
                 ) -> tuple:
    """One RK4 sub-evaluation. Returns the derivative of every
    continuous state element, same order as `state`. Guards against
    every division-by-zero this module could hit when combined with
    the rest of the pipeline: r->0 (degenerate/at planet center), m->0
    (fuel exhausted, no dry-mass floor supplied), v->0 (already guarded
    inside _aero_force_and_cop), inertia<=0 or None (torque skipped, not
    divided-by-zero), animation_time<=0 (handled in _update_gimbal_time,
    not called from here anyway -- gimbal is a discrete post-step, not
    part of this continuous derivative)."""
    px, py, vx, vy, m, theta, omega, heat_temp = state

    r = math.hypot(px, py)
    if r < 1.0:
        # Degenerate: at/through the planet's center. Freeze the
        # integration rather than dividing by ~0 or propagating inf/nan.
        return (0.0,) * _STATE_LEN

    h = r - body["radius_m"]
    m_safe = m if m > 1e-6 else 1e-6

    engines = (craft_config or {}).get("engines")
    parachutes = (craft_config or {}).get("parachutes")
    isp_multiplier = (craft_config or {}).get("isp_multiplier", 1.0)
    exposed_surface = (craft_config or {}).get("exposed_surface_for_heat", 0.0)

    if flags["gravity"]:
        g_mag = body["mu"] / (r * r)
        gx, gy = -g_mag * (px / r), -g_mag * (py / r)
    else:
        gx, gy = 0.0, 0.0

    fx_aero, fy_aero, cop_x, cop_y, _drag_area = _aero_force_and_cop(
        theta, vx, vy, omega, h, aoa_table, com_local, parachutes, body,
        flags["drag"], flags["parachute_drag"])

    fx_thr, fy_thr, mass_flow_engines, engine_levers = _engine_thrust(
        theta, engines, gimbal_times, isp_multiplier, flags["thrust"], flags["fuel_burn"])

    ax = gx + (fx_aero + fx_thr) / m_safe
    ay = gy + (fy_aero + fy_thr) / m_safe

    alpha = 0.0
    if inertia is not None and com_local is not None and inertia > 1e-9:
        comx, comy = com_local
        torque_z = 0.0
        if flags["aero_torque"] and cop_x is not None:
            torque_z += (cop_x - comx) * fy_aero - (cop_y - comy) * fx_aero
        if flags["thrust"]:
            for lx, ly, fx, fy in engine_levers:
                torque_z += lx * fy - ly * fx
        alpha = (torque_z / inertia) * RAD2DEG

    dm_dt = -(mass_flow_engines) if flags["fuel_burn"] else 0.0

    d_heat_dt = 0.0
    if flags["heat"]:
        v = math.hypot(vx, vy)
        v_radial = (vx * px + vy * py) / r
        density = atmospheric_density(h, body)
        air_temp = air_temperature(v, v_radial, density)
        d_heat_dt = _heat_derivative(heat_temp, air_temp, exposed_surface)

    return (vx, vy, ax, ay, dm_dt, omega, alpha, d_heat_dt)


def _rk4_step(state: tuple, body: dict, dt: float, aoa_table: Optional[dict],
              com_local: Optional[tuple], inertia: Optional[float],
              craft_config: Optional[dict], gimbal_times: list, flags: dict) -> tuple:
    def deriv(s):
        return _derivative(s, body, aoa_table, com_local, inertia, craft_config,
                            gimbal_times, flags)

    def plus(s, k, scale):
        return tuple(si + scale * ki for si, ki in zip(s, k))

    k1 = deriv(state)
    k2 = deriv(plus(state, k1, dt / 2))
    k3 = deriv(plus(state, k2, dt / 2))
    k4 = deriv(plus(state, k3, dt))

    return tuple(
        si + (dt / 6) * (a + 2 * b + 2 * c + d)
        for si, a, b, c, d in zip(state, k1, k2, k3, k4)
    )


def forward_simulate(start: dict, duration_s: float, dt: float = 0.25,
                      body_name: str = "Earth", aoa_table: Optional[dict] = None,
                      inertia: Optional[float] = None,
                      com_local: Optional[tuple[float, float]] = None,
                      torque_effective: Optional[float] = None,
                      flags: Optional[dict] = None,
                      craft_config: Optional[dict] = None,
                      staging_events: Optional[list] = None,
                      terrain_lookup: Optional[Callable[[float], float]] = None,
                      initial_gimbal_times: Optional[list] = None,
                      initial_heat_temp: float = 0.0) -> list[dict]:
    """Forward-integrates from a real telemetry sample's state for
    duration_s using RK4 for the continuous state and discrete post-step
    corrections for SAS/gimbal/RCS/staging/terrain. See module docstring
    for the full state model and every parameter's meaning.

    Backward-compatible fallback: if aoa_table is None, uses the OLD
    frozen-dragArea, no-rotation, no-Bucket-A behavior (unchanged from
    before this integration pass) -- none of engines/rcs_modules/
    parachutes/staging/terrain/heat apply in that path; it exists purely
    so old callers keep working unmodified.

    Returns a list of state-point dicts, one per step (first entry is
    the unmodified starting state). If terrain collision is detected
    (flags["terrain"] and either terrain_lookup or the flat-datum
    fallback), the list stops early at the colliding point (that point
    has "collided": True).
    """
    flags = _resolve_flags(flags)
    body = PLANET_CONSTANTS[body_name]
    px, py, vx, vy, m = start["px"], start["py"], start["vx"], start["vy"], start["m"]
    theta = start.get("rot", 0.0)
    omega = start.get("angv", 0.0)

    if aoa_table is None:
        # Backward-compatible fallback: frozen dragArea, no rotation, no
        # Bucket-A physics. Unchanged from the pre-2026-09-02 module.
        frozen_drag_area = start.get("dragArea") or 0.0

        def frozen_accel(px, py, vx, vy):
            r = math.hypot(px, py)
            if r == 0:
                return 0.0, 0.0
            if flags["gravity"]:
                g_mag = body["mu"] / (r * r)
                gx, gy = -g_mag * (px / r), -g_mag * (py / r)
            else:
                gx, gy = 0.0, 0.0
            if flags["drag"]:
                v_mag = math.hypot(vx, vy)
                h = r - body["radius_m"]
                density = atmospheric_density(h, body)
                if v_mag > 0 and density > 0:
                    f = 1.5 * frozen_drag_area * v_mag * v_mag * density
                    return gx - (vx / v_mag) * f / m, gy - (vy / v_mag) * f / m
            return gx, gy

        def frozen_rk4(px, py, vx, vy, dt):
            def deriv(px, py, vx, vy):
                ax, ay = frozen_accel(px, py, vx, vy)
                return vx, vy, ax, ay
            k1 = deriv(px, py, vx, vy)
            k2 = deriv(px+k1[0]*dt/2, py+k1[1]*dt/2, vx+k1[2]*dt/2, vy+k1[3]*dt/2)
            k3 = deriv(px+k2[0]*dt/2, py+k2[1]*dt/2, vx+k2[2]*dt/2, vy+k2[3]*dt/2)
            k4 = deriv(px+k3[0]*dt, py+k3[1]*dt, vx+k3[2]*dt, vy+k3[3]*dt)
            return (px + (dt/6)*(k1[0]+2*k2[0]+2*k3[0]+k4[0]),
                    py + (dt/6)*(k1[1]+2*k2[1]+2*k3[1]+k4[1]),
                    vx + (dt/6)*(k1[2]+2*k2[2]+2*k3[2]+k4[2]),
                    vy + (dt/6)*(k1[3]+2*k2[3]+2*k3[3]+k4[3]))

        points = [{"t": 0.0, "px": px, "py": py, "vx": vx, "vy": vy,
                   "h": math.hypot(px, py) - body["radius_m"], "v": math.hypot(vx, vy),
                   "theta_deg": theta, "omega_degs": omega, "aoa_deg": None,
                   "dragArea": frozen_drag_area}]
        steps = int(duration_s / dt)
        for i in range(steps):
            px, py, vx, vy = frozen_rk4(px, py, vx, vy, dt)
            if flags["sas"] and torque_effective is not None:
                omega = apply_sas(omega, m, torque_effective, dt)
            theta = _wrap180(theta + omega * dt)
            t = (i + 1) * dt
            points.append({"t": round(t, 3), "px": px, "py": py, "vx": vx, "vy": vy,
                            "h": math.hypot(px, py) - body["radius_m"], "v": math.hypot(vx, vy),
                            "theta_deg": theta, "omega_degs": omega, "aoa_deg": None,
                            "dragArea": frozen_drag_area})
        return points

    # ---- Full Bucket-A-integrated path ----
    engines = (craft_config or {}).get("engines") or []
    rcs_modules = (craft_config or {}).get("rcs_modules") or []
    dry_mass_t = (craft_config or {}).get("dry_mass_t")
    heat_tolerance_c = (craft_config or {}).get("heat_tolerance_c", 412.0)

    gimbal_times = list(initial_gimbal_times) if initial_gimbal_times else [0.0] * len(engines)
    heat_temp = initial_heat_temp

    staging_events = sorted(staging_events or [], key=lambda e: e["t"])
    staging_idx = 0

    def state_point(t, px, py, vx, vy, theta, omega, m, heat_temp, collided=False):
        heading = math.degrees(math.atan2(vy, vx)) if math.hypot(vx, vy) > 1e-6 else None
        aoa = _wrap180((theta + 90.0) - heading) if heading is not None else None
        drag_area = lookup_field(aoa_table, aoa, "dragArea") if aoa is not None else 0.0
        return {"t": t, "px": px, "py": py, "vx": vx, "vy": vy,
                "h": math.hypot(px, py) - body["radius_m"], "v": math.hypot(vx, vy),
                "theta_deg": theta, "omega_degs": omega, "aoa_deg": aoa,
                "dragArea": drag_area, "m": m, "heat_temp_c": heat_temp,
                "would_destroy": heat_temp >= heat_tolerance_c,
                "gimbal_times": list(gimbal_times), "collided": collided}

    points = [state_point(0.0, px, py, vx, vy, theta, omega, m, heat_temp)]
    steps = int(duration_s / dt)
    state = (px, py, vx, vy, m, theta, omega, heat_temp)

    for i in range(steps):
        t_after = (i + 1) * dt

        state = _rk4_step(state, body, dt, aoa_table, com_local, inertia,
                           craft_config, gimbal_times, flags)
        px, py, vx, vy, m, theta, omega, heat_temp = state
        theta = _wrap180(theta)

        # --- Discrete post-step corrections, in the confirmed real order:
        # output_TurnAxisTorque (SAS or manual) is computed FIRST from the
        # pre-correction omega, THEN used to both correct omega (SAS) AND
        # as gimbal's target (same broadcast signal, B1.10) -- so turn_axis
        # must be computed once, before SAS mutates omega, and reused for
        # both.
        turn_axis = compute_turn_axis(omega, m, torque_effective, dt)

        # RCS: discrete kick (see _rcs_force's docstring for why this is
        # discrete, not part of the continuous derivative).
        if flags["rcs"] and rcs_modules:
            fx_rcs, fy_rcs, rcs_levers = _rcs_force(theta, turn_axis, omega, rcs_modules, True)
            if fx_rcs or fy_rcs:
                m_safe = m if m > 1e-6 else 1e-6
                vx += (fx_rcs / m_safe) * dt
                vy += (fy_rcs / m_safe) * dt
                if inertia is not None and com_local is not None and inertia > 1e-9:
                    torque_z = sum(lx * fy - ly * fx
                                    for lx, ly, fx, fy, _th, _ct, _isp in rcs_levers)
                    omega += (torque_z / inertia) * RAD2DEG * dt
                if flags["fuel_burn"]:
                    rcs_mass_flow = sum(
                        thrust_ton * count / isp
                        for _lx, _ly, _fx, _fy, thrust_ton, count, isp in rcs_levers
                        if isp > 0
                    )
                    m -= rcs_mass_flow * dt

        if flags["sas"] and torque_effective is not None:
            omega = apply_sas(omega, m, torque_effective, dt)

        if flags["gimbal"] and engines:
            for idx, eng in enumerate(engines):
                if not eng.get("has_gimbal"):
                    continue
                rot_dir = eng.get("rotation_direction", 1.0)
                throttle = eng.get("throttle", 0.0)
                target = (turn_axis * rot_dir) if throttle > 0 else 0.0
                anim_t = eng.get("gimbal_animation_time_s")
                cur = gimbal_times[idx] if idx < len(gimbal_times) else 0.0
                new_val = _update_gimbal_time(cur, target, anim_t, dt)
                if idx < len(gimbal_times):
                    gimbal_times[idx] = new_val
                else:
                    gimbal_times.append(new_val)

        # Mass floor -- this module has no real tank-capacity tracking,
        # so without a supplied dry_mass_t, clamp to a small epsilon
        # instead of letting mass integrate through zero/negative.
        floor = dry_mass_t if dry_mass_t is not None else 1e-3
        if m < floor:
            m = floor

        if heat_temp < 0:
            heat_temp = 0.0

        # Staging: time-triggered, checked against this step's window.
        if flags["staging"]:
            while staging_idx < len(staging_events) and staging_events[staging_idx]["t"] <= t_after:
                ev = staging_events[staging_idx]
                ejected = ev.get("ejected_mass", 0.0)
                m_before_stage = m
                m = max(floor, m - ejected)
                actual_ejected = m_before_stage - m
                delta_v_local = ev.get("eject_delta_v_local")
                if delta_v_local is not None and actual_ejected > 1e-9 and m > 1e-9:
                    dvx_local, dvy_local = delta_v_local
                    dvx_world, dvy_world = _rotate_body_vector(dvx_local, dvy_local, theta)
                    # Momentum conservation: m_ej*dv_ej + m_cont*dv_cont = 0
                    ratio = -(actual_ejected / m)
                    vx += ratio * dvx_world
                    vy += ratio * dvy_world
                # omega/theta carry over unchanged (confirmed, section 2.7)
                staging_idx += 1

        # Terrain check -- flat-datum fallback (height=0) if no
        # terrain_lookup supplied. Conservative for real terrain above
        # datum, optimistic for anywhere below it (ocean basins) --
        # documented in the module docstring, not silently assumed
        # accurate.
        collided = False
        if flags["terrain"]:
            r = math.hypot(px, py)
            h_now = r - body["radius_m"]
            angle_deg = math.degrees(math.atan2(py, px))
            terrain_h = terrain_lookup(angle_deg) if terrain_lookup else 0.0
            if h_now <= terrain_h:
                collided = True

        state = (px, py, vx, vy, m, theta, omega, heat_temp)
        points.append(state_point(round(t_after, 3), px, py, vx, vy, theta, omega,
                                   m, heat_temp, collided=collided))
        if collided:
            break

    return points


def prep_demo_data(src_path: str, out_path: str, n_downsample: int = 2500,
                    aoa_table_path: Optional[str] = None,
                    inertia: Optional[float] = None,
                    com_local: Optional[tuple[float, float]] = None,
                    torque_effective: Optional[float] = None,
                    craft_config: Optional[dict] = None) -> dict:
    """Loads a real archived flight, downsamples it for embedding in an
    interactive artifact, and runs a self-test (10s forward-sim from a
    mid-flight sample, compared against the REAL recorded trajectory at
    the matching later timestamp) so the demo ships with a known,
    reported accuracy figure."""
    samples = []
    with open(src_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    aoa_table = None
    if aoa_table_path:
        aoa_table = json.loads(Path(aoa_table_path).read_text())

    n = len(samples)
    step = max(1, n // n_downsample)
    t0 = samples[0]["t"]
    downsampled = []
    for i in range(0, n, step):
        s = samples[i]
        downsampled.append({
            "idx": i, "t": round(s["t"] - t0, 3), "h": s.get("h"),
            "px": s.get("px"), "py": s.get("py"), "vx": s.get("vx"), "vy": s.get("vy"),
            "m": s.get("m"), "dragArea": s.get("dragArea"), "vv": s.get("vv"),
            "rot": s.get("rot"), "angv": s.get("angv"),
        })

    test_idx = n // 3
    test_start = samples[test_idx]
    sim = forward_simulate(test_start, 10.0, dt=0.1, aoa_table=aoa_table,
                            inertia=inertia, com_local=com_local,
                            torque_effective=torque_effective, craft_config=craft_config)
    target_t = test_start["t"] + 10.0
    real_at_target = min(samples, key=lambda s: abs(s["t"] - target_t))
    pred_final = sim[-1]
    h_error_pct = abs(pred_final["h"] - real_at_target["h"]) / max(abs(real_at_target["h"]), 1) * 100

    result = {
        "meta": {
            "total_real_samples": n,
            "downsampled_count": len(downsampled),
            "t0_absolute": t0,
            "planet_constants": PLANET_CONSTANTS["Earth"],
            "rotating_model": aoa_table is not None,
            "torque_model_active": aoa_table is not None and inertia is not None and com_local is not None,
            "sas_active": torque_effective is not None,
            "craft_config_active": craft_config is not None,
            "self_test": {
                "start_idx": test_idx, "start_t_rel": round(test_start["t"] - t0, 2),
                "duration_s": 10.0,
                "predicted_h": pred_final["h"], "real_h": real_at_target["h"],
                "h_error_pct": h_error_pct,
            },
        },
        "samples": downsampled,
    }
    Path(out_path).write_text(json.dumps(result))
    return result["meta"]


if __name__ == "__main__":
    meta = prep_demo_data(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2500)
    print(f"wrote {sys.argv[2]}: {meta['downsampled_count']} downsampled points "
          f"from {meta['total_real_samples']} real samples")
    print(f"self-test: 10s forward-sim from idx {meta['self_test']['start_idx']} -> "
          f"h_error_pct={meta['self_test']['h_error_pct']:.4f}%")
