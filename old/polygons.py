import cmath
import math
import random
import re
import threading
import time

# ==============================================================================
# RIGOROUS MATHEMATICAL & BALANCED RHYTHM ENGINE
# ==============================================================================

def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a

def bjorklund(steps: int, pulses: int) -> list[int]:
    """Generates standard Bjorklund Euclidean rhythm E(pulses, steps)."""
    if pulses <= 0: return [0] * steps
    if pulses >= steps: return [1] * steps

    pattern = [[1] for _ in range(pulses)]
    remainder = [[0] for _ in range(steps - pulses)]

    while len(remainder) > 1:
        count = min(len(pattern), len(remainder))
        for i in range(count):
            pattern[i].extend(remainder.pop(0))

    pattern.extend(remainder)
    return [bit for group in pattern for bit in group]

def get_centroid(pattern: list[int], N: int) -> tuple[float, float]:
    if not pattern or sum(pattern) == 0:
        return 0.0, 0.0
    total_vector = 0j
    for i, active in enumerate(pattern):
        if active:
            angle = 2 * math.pi * i / N
            total_vector += cmath.exp(1j * angle)
    center = total_vector / sum(pattern)
    return center.real, center.imag

def is_strictly_balanced(pattern: list[int], N: int, tol: float = 1e-5) -> bool:
    cx, cy = get_centroid(pattern, N)
    return math.hypot(cx, cy) < tol

def is_regular_polygon(pattern: list[int], N: int) -> bool:
    k = sum(pattern)
    if k < 2 or N % k != 0:
        return False
    stride = N // k
    active_indices = [i for i, b in enumerate(pattern) if b]
    start = active_indices[0]
    expected = [(start + j * stride) % N for j in range(k)]
    return sorted(active_indices) == sorted(expected)

def analyze_pattern(pattern: list[int], N: int) -> dict:
    cx, cy = get_centroid(pattern, N)
    balanced = is_strictly_balanced(pattern, N)
    regular = is_regular_polygon(pattern, N) if balanced else False
    class_type = "Class 1 (Regular)" if regular else ("Class 2 (Composite)" if balanced else "Unbalanced")
    
    return {
        "pattern": pattern,
        "is_balanced": balanced,
        "class_type": class_type,
        "centroid": [round(cx, 5), round(cy, 5)],
        "dist_from_origin": round(math.hypot(cx, cy), 5)
    }

def get_canonical_dihedral(pattern: list[int]) -> tuple[int, ...]:
    """Returns lexicographically smallest representation under rotation AND reflection (D_N)."""
    n = len(pattern)
    rotations = [tuple(pattern[i:] + pattern[:i]) for i in range(n)]
    rev = pattern[::-1]
    reflections = [tuple(rev[i:] + rev[:i]) for i in range(n)]
    return min(rotations + reflections)

def get_full_orbit(pattern: list[int]) -> list[list[int]]:
    """Generates all unique rotational and reflective realizations of a pattern."""
    n = len(pattern)
    rev = pattern[::-1]
    seen = set()
    orbit = []
    
    for i in range(n):
        r = tuple(pattern[i:] + pattern[:i])
        if r not in seen:
            seen.add(r)
            orbit.append(list(r))
            
        ref = tuple(rev[i:] + rev[:i])
        if ref not in seen:
            seen.add(ref)
            orbit.append(list(ref))
            
    return orbit

def circular_distance(pat1: list[int], pat2: list[int]) -> float:
    """Calculates rotational distance and density difference between two patterns."""
    N = len(pat1)
    idx1 = [i for i, x in enumerate(pat1) if x]
    idx2 = [i for i, x in enumerate(pat2) if x]
    
    if not idx1 and not idx2: return 0.0
    if not idx1 or not idx2: return float(N)
    
    dist = 0
    for p1 in idx1:
        dist += min(min(abs(p1 - p2), N - abs(p1 - p2)) for p2 in idx2)
    for p2 in idx2:
        dist += min(min(abs(p2 - p1), N - abs(p2 - p1)) for p1 in idx1)
        
    density_penalty = abs(len(idx1) - len(idx2)) * (N / 4.0)
    return dist + density_penalty

def generate_rhythm_library(N: int) -> dict:
    """
    Generates all unique non-trivial balanced patterns for N steps (D_N canonicalized),
    including cyclotomic basis combinations and Bjorklund rhythms.
    """
    cyclotomic = []
    bjorklund_rhythms = []
    seen_cyc = set()
    seen_bjork = set()

    # 1. Euclidean / Bjorklund Rhythms
    for k in range(1, N):
        pat = bjorklund(N, k)
        canonical = get_canonical_dihedral(pat)
        if canonical not in seen_bjork:
            seen_bjork.add(canonical)
            info = analyze_pattern(list(canonical), N)
            info["label"] = f"Euclidean E({k},{N})"
            info["is_coprime"] = gcd(k, N) == 1
            bjorklund_rhythms.append(info)

    # 2. Constructive Cyclotomic Generation
    divisors = [d for d in range(2, N) if N % d == 0]
    basis_polygons = []

    for d in divisors:
        stride = N // d
        for offset in range(stride):
            pat_set = frozenset(offset + i * stride for i in range(d))
            basis_polygons.append(pat_set)

    def build_balanced_combinations(index: int, current_union: frozenset):
        if len(seen_cyc) > 5000:
            return

        if current_union:
            canonical = get_canonical_dihedral([1 if i in current_union else 0 for i in range(N)])
            if canonical not in seen_cyc:
                seen_cyc.add(canonical)
                canonical_pat = list(canonical)
                info = analyze_pattern(canonical_pat, N)
                info["label"] = f"Cyclotomic {info['class_type']} ({sum(canonical_pat)} pulses)"
                cyclotomic.append(info)

        for i in range(index, len(basis_polygons)):
            if not current_union.intersection(basis_polygons[i]):
                build_balanced_combinations(i + 1, current_union.union(basis_polygons[i]))

    build_balanced_combinations(0, frozenset())

    return {
        "cyclotomic": cyclotomic,
        "bjorklund": bjorklund_rhythms
    }

def is_nontrivial(pattern: list[int]) -> bool:
    """Excludes trivial patterns that have fewer than 2 beats or fewer than 2 rests."""
    k = sum(pattern)
    n = len(pattern)
    return 1 < k < (n - 1)

def note_to_freq_432(note_str: str) -> float:
    match = re.match(r"^([A-Ga-g][#b]?)(-?\d+)$", note_str.strip())
    if not match:
        return 432.0
    
    note_name, octave_str = match.groups()
    octave = int(octave_str)
    
    semitone_offsets = {
        'C': -9, 'C#': -8, 'Db': -8, 'D': -7, 'D#': -6, 'Eb': -6,
        'E': -5, 'F': -4, 'F#': -3, 'Gb': -3, 'G': -2, 'G#': -1,
        'Ab': -1, 'A': 0, 'A#': 1, 'Bb': 1, 'B': 2
    }
    
    clean_note = note_name.capitalize()
    semitone = semitone_offsets.get(clean_note, 0)
    midi_num = (octave + 1) * 12 + semitone + 9
    return 432.0 * math.pow(2, (midi_num - 69) / 12.0)

# ==============================================================================
# NESTED POLYGON PROGRESSION ENGINE
# ==============================================================================

class PolygonProgressionEngine:
    """
    Iterates through all valid pairwise combinations of balanced polygons in their
    full rotational and reflective realizations, traversed in a smooth path.
    """
    def __init__(self, step_cycles=list(range(8, 21)), repeats_per_combo=7, bpm=60, ws_port=65403, shuffle_n=True):
        self.step_cycles = step_cycles
        self.shuffle_n = shuffle_n
        self.repeats_per_combo = repeats_per_combo
        self.bpm = bpm
        self.ws_port = ws_port
        self.connected_clients = set()

        self.current_n_idx = 0
        self.sequence = []
        self.combo_idx = 0
        self.current_repeat = 0
        self.step_in_pattern = 0

        self.lock = threading.Lock()
        self.current_state = {}

        self._load_combos_for_n(self.step_cycles[self.current_n_idx])

    def _get_expanded_balanced_polygons(self, N: int) -> list[dict]:
        """
        Gets all canonical shapes for N, then expands each into all its distinct
        reflection and rotation realizations.
        """
        lib = generate_rhythm_library(N)
        canonical_pats = []
        seen_canon = set()
        for group in [lib.get("bjorklund", []), lib.get("cyclotomic", [])]:
            for info in group:
                pat = info["pattern"]
                canon_key = tuple(get_canonical_dihedral(pat))
                if canon_key not in seen_canon and is_nontrivial(pat):
                    seen_canon.add(canon_key)
                    canonical_pats.append(info)

        expanded_pats = []
        for info in canonical_pats:
            orbit = get_full_orbit(info["pattern"])
            for idx, realization in enumerate(orbit):
                realization_info = analyze_pattern(realization, N)
                realization_info["label"] = f"{info['label']} (Var {idx + 1}/{len(orbit)})"
                expanded_pats.append(realization_info)

        return expanded_pats

#    def _sequence_smooth_pair_path(self, combos: list[dict]) -> list[dict]:
#        """Sorts pairwise combinations minimizing circular distance across both positive and negative components."""
#        if not combos: return []
#
#        unvisited = combos[:]
#        path = [unvisited.pop(0)]
#
#        while unvisited:
#            curr_pos = path[-1]["pos"]["pattern"]
#            curr_neg = path[-1]["neg"]["pattern"]
#
#            closest_idx = 0
#            min_dist = float('inf')
#
#            for i, cand in enumerate(unvisited):
#                d_pos = circular_distance(curr_pos, cand["pos"]["pattern"])
#                d_neg = circular_distance(curr_neg, cand["neg"]["pattern"])
#                total_dist = d_pos + d_neg
#                
#                if total_dist < min_dist:
#                    min_dist = total_dist
#                    closest_idx = i
#
#            path.append(unvisited.pop(closest_idx))
#
#        return path

    def _sequence_smooth_pair_path(self, combos: list[dict], shuffle_start: bool = True) -> list[dict]:
        if not combos: return []
    
        unvisited = combos[:]
        # Pick a random starting seed on repeats to generate a distinct smooth trajectory
        start_idx = random.randrange(len(unvisited)) if shuffle_start else 0
        path = [unvisited.pop(start_idx)]
    
        while unvisited:
            curr_pos = path[-1]["pos"]["pattern"]
            curr_neg = path[-1]["neg"]["pattern"]
    
            closest_idx = 0
            min_dist = float('inf')
    
            for i, cand in enumerate(unvisited):
                d_pos = circular_distance(curr_pos, cand["pos"]["pattern"])
                d_neg = circular_distance(curr_neg, cand["neg"]["pattern"])
                total_dist = d_pos + d_neg
    
                if total_dist < min_dist:
                    min_dist = total_dist
                    closest_idx = i
    
            path.append(unvisited.pop(closest_idx))
    
        return path

    def _load_combos_for_n(self, N: int):
        balanced_expanded = self._get_expanded_balanced_polygons(N)
        combos = []
        
        # Pairwise iteration over all rotational and reflective realizations
        for pos_info in balanced_expanded:
            pos_pat = pos_info["pattern"]
            for neg_info in balanced_expanded:
                neg_pat = neg_info["pattern"]
                
                # Bitwise subtraction: Positive MINUS Negative
                sub_pat = [1 if (p and not q) else 0 for p, q in zip(pos_pat, neg_pat)]
                
                if is_nontrivial(sub_pat):
                    combos.append({
                        "N": N,
                        "pos": pos_info,
                        "neg": neg_info,
                        "sub_pattern": sub_pat,
                        "sub_analysis": analyze_pattern(sub_pat, N)
                    })

        # Smooth pairwise traversal
        self.sequence = self._sequence_smooth_pair_path(combos)
        self.combo_idx = 0
        self.current_repeat = 0
        self.step_in_pattern = 0
        
        if not combos:
            self._advance_n()

#    def _advance_n(self):
#        self.current_n_idx = (self.current_n_idx + 1) % len(self.step_cycles)
#        self._load_combos_for_n(self.step_cycles[self.current_n_idx])
    def _advance_n(self):
        self.current_n_idx += 1
        if self.current_n_idx >= len(self.step_cycles):
            self.current_n_idx = 0
            if self.shuffle_n:
                random.shuffle(self.step_cycles)  # Reshuffle N order on macro-cycle wrap
                
        self._load_combos_for_n(self.step_cycles[self.current_n_idx])

    def tick(self) -> dict:
        with self.lock:
            if not self.sequence:
                self._advance_n()
                if not self.sequence:
                    return {}

            curr_combo = self.sequence[self.combo_idx]
            N = curr_combo["N"]
            pos_pat = curr_combo["pos"]["pattern"]
            neg_pat = curr_combo["neg"]["pattern"]
            sub_pat = curr_combo["sub_pattern"]

            eval_idx = self.step_in_pattern % N
            pos_hit = bool(pos_pat[eval_idx])
            neg_hit = bool(neg_pat[eval_idx])
            sub_hit = bool(sub_pat[eval_idx])

            state = {
                "N": N,
                "step_index": eval_idx,
                "repeat_count": self.current_repeat + 1,
                "total_repeats": self.repeats_per_combo,
                "combo_index": self.combo_idx + 1,
                "total_combos": len(self.sequence),
                "pos_polygon": curr_combo["pos"],
                "neg_polygon": curr_combo["neg"],
                "sub_pattern": sub_pat,
                "sub_analysis": curr_combo["sub_analysis"],
                "hits": {
                    "left_hand_7th": pos_hit,
                    "right_hand_7th": sub_hit,
                    "neg_hit": neg_hit
                },
                "timestamp": time.time()
            }
            self.current_state = state

            self.step_in_pattern += 1
            if self.step_in_pattern >= N:
                self.step_in_pattern = 0
                self.current_repeat += 1
                if self.current_repeat >= self.repeats_per_combo:
                    self.current_repeat = 0
                    self.combo_idx += 1
                    if self.combo_idx >= len(self.sequence):
                        self._advance_n()

            return state

# Global engine instance defaulting to 8-20 beats
polygon_engine = PolygonProgressionEngine(step_cycles=list(range(8, 21)), repeats_per_combo=7, bpm=60)
