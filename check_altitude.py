import sys, math
sys.path.insert(0, "analysis")
import agent_interface as ai
import forward_sim as fsim
snap = ai.observe(use_tcp=True)
px = snap.get("location.position.x", 0.0)
py = snap.get("location.position.y", 0.0)
r = math.hypot(px, py)
body = fsim.PLANET_CONSTANTS["Earth"]
alt = r - body["radius_m"]
vy = snap.get("location.velocity.y", 0.0)
# rb2d.rotation is already degrees (Unity Rigidbody2D convention,
# confirmed live via setrot) -- no math.degrees() conversion.
rot = snap.get("rb2d.rotation", 0.0)
print(f"altitude={alt:.1f}m vertical_speed={vy:.1f}m/s rotation={rot:.1f}deg")
