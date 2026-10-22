"""Versioned synthetic movement/decision heuristics; not professional tracking."""
import math

from simulator.pitch import point, distance, resolve_pass


def targets(pitch, team, owner, ball, press=False, carry=False):
    """Role shape, support triangles, one presser, covering defenders, spacing."""
    result = {}
    enemy = "away" if team == "home" else "home"
    opponents = pitch.team_positions(enemy)
    chasers = sorted((p for p in opponents if pitch.slots[p] != 1),
                     key=lambda p: distance(opponents[p], ball))[:2]
    d = pitch.direction(team)
    defence = sorted(d*p["x_m"] for p in opponents.values())[-2]
    for pid, pos in pitch.positions.items():
        side, slot = pid.split("-")[0], pitch.slots[pid]
        direction = pitch.direction(side)
        if slot == 1:
            depth = 3 + min(5, max(0, direction*(ball["x_m"]-52.5))/12)
            goal_x = depth if direction == 1 else 105-depth
            result[pid] = point(goal_x, max(29, min(39, 34+(ball["y_m"]-34)*.22)))
            continue
        ax, ay = pitch.FORMATION[slot-1]
        local_ball = ball["x_m"] if direction == 1 else 105-ball["x_m"]
        if side == team:
            if slot <= 5:
                x = .38*ax + .62*(local_ball-18)
            elif slot <= 8:
                x = local_ball + (-8 if slot == 7 else 5)
            else:
                x = min(96, local_ball+(14 if slot == 10 else 9))
                # Keep a receiving option onside rather than running straight
                # through the defensive line at every formation update.
                x = min(x, (defence if d == 1 else 105+defence)-1)
            y = ay*.88+ball["y_m"]*.12
            if slot in (2, 5, 9, 11):
                y = ay*.92+ball["y_m"]*.08
        else:
            x = .65*ax+.35*(local_ball-6)
            y = ay*.7+ball["y_m"]*.3
        target = point(x if direction == 1 else 105-x, y)
        if pid in chasers:
            rank = chasers.index(pid)
            if rank == 0 and (press or distance(pos, ball) < 18):
                target = point(ball["x_m"]-direction*(1.2 if press else 2.3), ball["y_m"])
            elif rank == 1:
                target = point(ball["x_m"]+direction*6, ball["y_m"]+(4 if pos["y_m"]>ball["y_m"] else -4))
        if pid == owner:
            if not carry or slot == 1:
                target = ball.copy()
            else:
                # Choose a short progressive route with actual opponent space.
                candidates = [point(ball["x_m"]+direction*6, ball["y_m"]+dy) for dy in (-5,0,5)]
                target = max(candidates, key=lambda p: min(distance(p,q) for q in opponents.values())-.08*abs(p["y_m"]-34))
                if min(distance(ball,q) for q in opponents.values()) < 2:
                    target = ball.copy()  # shield and release rather than run through a tackler
        result[pid] = target
    # Repulsion is based on one common frame, so iteration order cannot make
    # players repel positions that have already advanced within this tick.
    for pid, target in result.items():
        if pid == owner:
            continue
        pos = pitch.positions[pid]
        for mate, q in pitch.team_positions(pid.split("-")[0]).items():
            gap = distance(pos,q)
            if mate != pid and .001 < gap < 5:
                target = point(target["x_m"]+(pos["x_m"]-q["x_m"])/gap*(5-gap),
                               target["y_m"]+(pos["y_m"]-q["y_m"])/gap*(5-gap))
        result[pid] = target
    return result


def advance(pitch, milliseconds, team, owner, ball, start_ms, press=False, carry=False, contacts=None, ball_path=None):
    """Integrate at <=200ms, publish 500ms anchors and the exact final state.

    Planned contact actors take a straight receiving/intercepting run consistent
    with the resolver. Other actors use acceleration-limited steering.
    """
    velocities = getattr(pitch, "velocities", {})
    pitch.velocities = {p: velocities.get(p,(0.,0.)) for p in pitch.positions}
    initial = {p:q.copy() for p,q in pitch.positions.items()}
    samples = [{"period_time_ms": start_ms, "players": initial, "ball": ball.copy()}]
    elapsed, next_sample = 0, 500
    initial_ball = ball.copy()
    while elapsed < milliseconds:
        step = min(200, milliseconds-elapsed, next_sample-elapsed)
        dt = step/1000
        if ball_path:
            a,b = ball_path
            u = elapsed/milliseconds
            ball = point(a["x_m"]+(b["x_m"]-a["x_m"])*u,a["y_m"]+(b["y_m"]-a["y_m"])*u)
        if elapsed == 0 or elapsed % 500 == 0:
            desired = targets(pitch,team,owner,ball,press,carry)
        elapsed += step
        for pid, pos in list(pitch.positions.items()):
            if pid in (contacts or {}):
                target = contacts[pid]
                u = elapsed/milliseconds
                origin = initial[pid]
                pitch.positions[pid] = point(origin["x_m"]+(target["x_m"]-origin["x_m"])*u,
                                             origin["y_m"]+(target["y_m"]-origin["y_m"])*u)
                pitch.velocities[pid] = ((target["x_m"]-origin["x_m"])/(milliseconds/1000),
                                         (target["y_m"]-origin["y_m"])/(milliseconds/1000))
                continue
            target = desired[pid]
            dx,dy = target["x_m"]-pos["x_m"],target["y_m"]-pos["y_m"]
            gap = math.hypot(dx,dy)
            cap = 2.4 if pid == owner and carry else 4.5
            speed = min(cap, math.sqrt(2*2.5*gap))
            wanted = (dx/gap*speed,dy/gap*speed) if gap else (0,0)
            vx,vy = pitch.velocities[pid]
            previous_speed = math.hypot(vx,vy)
            if previous_speed > 4.5:
                vx,vy = vx*4.5/previous_speed,vy*4.5/previous_speed
            ax,ay = wanted[0]-vx,wanted[1]-vy
            norm = math.hypot(ax,ay)
            fraction = min(1,2.5*dt/norm) if norm else 1
            vx,vy = vx+ax*fraction,vy+ay*fraction
            pitch.positions[pid] = point(pos["x_m"]+vx*dt,pos["y_m"]+vy*dt)
            pitch.velocities[pid] = (vx,vy)
        if carry:
            ball = pitch.positions[owner].copy()
        if elapsed == next_sample or elapsed == milliseconds:
            samples.append({"period_time_ms": start_ms+elapsed,
                            "players": {p:q.copy() for p,q in pitch.positions.items()}, "ball": ball.copy()})
            next_sample += 500
    return samples, ball if carry else initial_ball


def passing_options(pitch, owner, ball, quiet=False, previous_passer=None):
    team = owner.split("-")[0]
    defenders = pitch.team_positions("away" if team == "home" else "home")
    options = []
    for pid, pos in pitch.team_positions(team).items():
        length = distance(ball,pos)
        if pid == owner or not 3 < length < 52:
            continue
        vx,vy = getattr(pitch,"velocities",{}).get(pid,(0,0))
        lead = min(.6,length/16*.45)
        target = point(pos["x_m"]+vx*lead,pos["y_m"]+vy*lead)
        speed = min(24,8+.28*distance(ball,target)+1.8)
        result = resolve_pass(ball,target,target,defenders,speed,True,reaction_s=.25,receiver_start=pos)
        progress = pitch.direction(team)*(target["x_m"]-ball["x_m"])
        space = min(distance(target,q) for q in defenders.values())
        score = math.exp(-((length-16)/21)**2)*(1+min(space,12)/8)
        score *= math.exp(max(-20,min(25,progress))*(.025 if quiet else .055))
        score *= .08 if result["interceptor_id"] else 1
        score *= .45 if pid == previous_passer else 1
        options.append({"player_id":pid,"target":target,"score":max(.0001,score),
                        "predicted_interceptor_id":result["interceptor_id"]})
    return options
