"""Evidence detectors — each takes the canonical profile and returns zero or
more `Evidence` entries with a per-candidate contribution (spec section 16).

Strength hierarchy actually enforced here (spec section 10):
  track name / free-text label   -> "weak"
  technical flag (forced/default, container structure) -> "medium"/"strong"
  codec/profile/bitrate reality  -> "medium"/"strong"
  exact structural fact (single-file container, resolution) -> "strong"/"very_strong"

No single detector is allowed to decide a candidate by itself — every one of
them contributes at most a partial nudge, and scoring.py sums many of them.
In particular (spec section 27): PGS alone doesn't imply BDRemux, TrueHD alone
doesn't imply BDRemux, E-AC-3 alone doesn't imply WEB-DL, 1080i alone doesn't
imply HDTV, SD resolution alone doesn't imply DVD — each of those is one
input among several below, weighted down by `reliability`/`strength` so it
can be outvoted by the rest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import CANDIDATES

STRENGTH_WEIGHT = {"weak": 0.35, "medium": 0.7, "strong": 1.0, "very_strong": 1.35}


@dataclass
class Evidence:
    feature: str
    value: Any
    contributions: dict[str, float]
    strength: str
    reliability: float
    explanation: str

    def effective(self) -> dict[str, float]:
        w = STRENGTH_WEIGHT.get(self.strength, 0.7) * max(0.0, min(1.0, self.reliability))
        return {k: v * w for k, v in self.contributions.items()}


def _zero() -> dict[str, float]:
    return {c: 0.0 for c in CANDIDATES}


def _c(**kwargs: float) -> dict[str, float]:
    d = _zero()
    d.update(kwargs)
    return d


def _range_score(value: float | None, lo: float, hi: float, peak: float = 20.0, tail: float = 0.55) -> float:
    """Peaks at `peak` inside [lo, hi], decays smoothly outside it. Used for
    every bitrate-normalization-based signal below instead of a hard cutoff."""
    if value is None:
        return 0.0
    if lo <= value <= hi:
        return peak
    width = (hi - lo) or 1e-6
    if value < lo:
        dist = (lo - value) / width
    else:
        dist = (value - hi) / width
    return peak * (tail ** min(dist, 6.0))


# ---------------------------------------------------------------------------
# Structural evidence (spec sections 15, 18)
# ---------------------------------------------------------------------------

def structural_single_file(profile: dict) -> list[Evidence]:
    """A single .mkv/.mp4 can never BE a Full BD/DVD image — FBD/FDVD always
    take an extreme structural penalty, but stay in the ranking (spec
    section 18: hard constraints reduce scores, never remove a candidate)."""
    return [Evidence(
        feature="single_file_container", value=True,
        contributions=_c(**{"FBD": -90.0, "FDVD": -90.0}),
        strength="very_strong", reliability=0.98,
        explanation="Un único archivo .mkv/.mp4 no puede representar una imagen completa de disco Blu-ray o DVD.",
    )]


def container_format(profile: dict) -> list[Evidence]:
    fmt = (profile["container"].get("format") or "").lower()
    ev: list[Evidence] = []
    if "matroska" in fmt:
        ev.append(Evidence(
            feature="container_format", value="Matroska",
            contributions=_c(BDRemux=4, BluRay=4, MHD=4, **{"WEB-DL": 3, "WEBRIP": 3}, HDTV=2, SD=1),
            strength="weak", reliability=0.6,
            explanation="Matroska es el contenedor habitual para cualquier tier de encode/remux; aporta poco por sí solo.",
        ))
    elif "mpeg-4" in fmt or "quicktime" in fmt:
        ev.append(Evidence(
            feature="container_format", value="MPEG-4",
            contributions=_c(**{"WEB-DL": 6, "WEBRIP": 4}, HDTV=1),
            strength="weak", reliability=0.55,
            explanation="MP4/MOV es el empaquetado nativo de la mayoría de plataformas de streaming.",
        ))
    return ev


def container_fragmentation(profile: dict) -> list[Evidence]:
    if not profile["container"].get("is_fragmented"):
        return []
    return [Evidence(
        feature="fragmented_mp4", value=True,
        contributions=_c(**{"WEB-DL": 10}),
        strength="medium", reliability=0.7,
        explanation="MP4 fragmentado (fMP4) es la forma nativa en que la mayoría de plataformas de streaming sirven vídeo.",
    )]


def chapters_signal(profile: dict) -> list[Evidence]:
    n = profile["topology"].get("chapter_count") or 0
    if n >= 6:
        return [Evidence(
            feature="chapter_count", value=n,
            contributions=_c(**{"FBD": 5, "FDVD": 5, "BDRemux": 8, "BluRay": 6, "MHD": 3}),
            strength="medium", reliability=0.65,
            explanation=f"{n} capítulos es típico de una fuente de disco (Blu-ray/DVD conservan su propia estructura de capítulos).",
        )]
    if n == 0:
        return [Evidence(
            feature="chapter_count", value=0,
            contributions=_c(**{"WEB-DL": 4, "WEBRIP": 4, "HDTV": 3, "SD": 2}),
            strength="weak", reliability=0.4,
            explanation="Sin capítulos, más habitual en rips web o de emisión que en fuentes de disco.",
        )]
    return []


# ---------------------------------------------------------------------------
# Resolution / scan type (spec sections 12, 15)
# ---------------------------------------------------------------------------

def resolution_signal(profile: dict) -> list[Evidence]:
    w, h = profile["video"].get("width") or 0, profile["video"].get("height") or 0
    ev: list[Evidence] = []
    if h and h <= 576:
        ev.append(Evidence(
            feature="resolution_sd", value=(w, h),
            contributions=_c(SD=18, HDTV=6, **{"FBD": -10, "FDVD": 5, "BDRemux": -25, "BluRay": -15, "MHD": -20, "WEB-DL": -5}),
            strength="medium", reliability=0.6,
            explanation=f"Resolución SD ({w}x{h}) es compatible con DVD/HDTV de definición estándar; incompatible con un BDRemux/MicroHD real.",
        ))
    elif h and h >= 2000:
        ev.append(Evidence(
            feature="resolution_uhd", value=(w, h),
            contributions=_c(**{"SD": -30, "HDTV": -20, "FDVD": -20}),
            strength="medium", reliability=0.7,
            explanation=f"Resolución UHD ({w}x{h}) descarta fuentes DVD/HDTV de definición estándar.",
        ))
    return ev


def scan_type_signal(profile: dict) -> list[Evidence]:
    scan = (profile["video"].get("scan_type") or "").lower()
    if scan.startswith("interlaced") or scan.startswith("mbaff") or scan.startswith("paff"):
        return [Evidence(
            feature="scan_type", value=scan,
            contributions=_c(HDTV=12, SD=6, **{"BDRemux": -8, "WEB-DL": -6}),
            strength="medium", reliability=0.55,
            explanation="Vídeo entrelazado es mucho más habitual en emisión de TV que en discos o streaming actuales.",
        )]
    return []


def hdr_dv_signal(profile: dict) -> list[Evidence]:
    v = profile["video"]
    if not (v.get("hdr") or v.get("dolby_vision")):
        return []
    label = "Dolby Vision" if v.get("dolby_vision") else "HDR"
    return [Evidence(
        feature="hdr_or_dv", value=label,
        contributions=_c(**{"WEB-DL": 6, "BDRemux": 6, "BluRay": 4, "SD": -20, "HDTV": -20, "FDVD": -20}),
        strength="medium", reliability=0.75,
        explanation=f"{label} es propio de masters 4K/premium modernos, incompatible con SD/HDTV/DVD.",
    )]


def video_codec_signal(profile: dict) -> list[Evidence]:
    codec = (profile["video"].get("codec") or "").lower()
    if not codec:
        return []
    if "mpeg-2" in codec or codec == "mpeg video" or "mpeg2" in codec:
        return [Evidence(
            feature="video_codec", value=codec,
            contributions=_c(SD=10, HDTV=10, **{"BDRemux": -12, "WEB-DL": -12, "WEBRIP": -8, "MHD": -10}),
            strength="medium", reliability=0.6,
            explanation="MPEG-2 es el códec habitual de DVD y emisión de TV; raro en encodes/rips modernos.",
        )]
    if "vc-1" in codec:
        return [Evidence(
            feature="video_codec", value=codec,
            contributions=_c(BDRemux=6, BluRay=6, **{"SD": -10, "HDTV": -10}),
            strength="weak", reliability=0.5,
            explanation="VC-1 se usó en algunos masters de Blu-ray; poco habitual en DVD o emisión.",
        )]
    if "av1" in codec or "vp9" in codec:
        return [Evidence(
            feature="video_codec", value=codec,
            contributions=_c(**{"WEB-DL": 8, "WEBRIP": 6}, **{"SD": -15, "HDTV": -15, "FDVD": -15}),
            strength="weak", reliability=0.5,
            explanation=f"{codec.upper()} es un códec moderno de distribución web; prácticamente inexistente en discos físicos o emisión.",
        )]
    return []


def bluray_compat_flag(profile: dict) -> list[Evidence]:
    settings = profile["video"].get("encoder_settings") or ""
    if "bluray_compat=1" in settings.replace(" ", ""):
        return [Evidence(
            feature="x264_bluray_compat", value=True,
            contributions=_c(BluRay=14, MHD=10, **{"FBD": 4}),
            strength="strong", reliability=0.85,
            explanation="El propio encoder x264 marca `bluray_compat=1`: el encode se generó explícitamente para cumplir el estándar Blu-ray.",
        )]
    return []


# ---------------------------------------------------------------------------
# Bitrate normalization (spec sections 11-12) — the core signal, always
# resolution/fps-aware, never a flat Mbps cutoff.
# ---------------------------------------------------------------------------

# (low, high) "sweet spot" of bits-per-pixel-per-frame per tier — the
# (p25, p75) percentiles observed over ~1300 real, name-labeled library
# files (calibration pass, 2026-07; see docs/source_engine.md). BDRemux had
# zero real samples in that library and keeps its original rough estimate.
#
# FBD/FDVD/SD are deliberately absent from this table (bpppf contributes
# nothing for them, always 0) rather than filled with an unvalidated guess:
# - FBD/FDVD: a Full BD/DVD image can't even be represented by the single
#   file this engine analyzes — `structural_single_file` above already
#   penalizes them hard on that basis alone; their video bitrate itself is
#   irrelevant to telling them apart from BDRemux/DVD-SD (a Full BD's main
#   feature stream IS essentially the same bitrate as a BDRemux of it —
#   they differ by disc structure, not bitrate).
# - SD: MPEG-2 (the DVD-era codec) is markedly less efficient than AVC/HEVC
#   — a genuine untouched DVD rip commonly lands at a MODERATE-TO-HIGH
#   bpppf despite its low absolute Mbps, because bpppf only normalizes for
#   pixel count/fps, not codec efficiency. A first version of this range
#   assumed "old format = low bitrate", which is backwards once normalized.
#   Rather than guess a corrected number with zero real SD samples to check
#   it against, SD detection is left entirely to `resolution_signal` (SD
#   height) and `video_codec_signal` (MPEG-2/DivX/Xvid) below, which don't
#   have this confound.
#
# The calibration's main finding for the tiers that DO have real samples:
# these ranges overlap heavily in practice (e.g. BluRay's own p25-p75 is
# 0.035-0.188, almost the whole practical range) — bpppf alone is a much
# weaker discriminator than initially assumed, which is why `peak`/
# reliability were both turned down from the pre-calibration version. It
# still helps (confirmed by the same pass), it just shouldn't dominate the
# way a single "strong" signal would.
#
# BDRemux and MHD's ranges below come from a SECOND calibration pass (same
# date) against the full eMuwarez torrent catalog (~11k torrents, name +
# resolution + size only, no MediaInfo) — the personal-library pass had
# zero BDRemux samples and only 8 for MHD. That catalog has no duration
# field, so bpppf there is an ESTIMATE (movies only, assumed 110min@24fps),
# noisier than the personal library's real MediaInfo-measured values —
# used only to fill gaps, not to override WEB-DL/WEBRIP/BluRay/HDTV (which
# keep the more precise personal-library numbers). BDRemux's real p25-p75
# (n=199) turned out to be 0.401-0.716 — much higher than the original
# unvalidated guess (0.20-0.55), confirming it's the highest-bitrate tier
# of all (essentially tied with FBD, which doesn't use this signal at all
# — see the note above on FBD/FDVD).
_BPPF_RANGES = {
    "BDRemux": (0.40, 0.72),      # catalog-calibrated, n=199 (estimated duration — see above)
    "BluRay": (0.035, 0.188),
    # Re-calibrated (2026-07) against 28 real MHD + 149 real BluRay catalog
    # movies using ACTUAL TMDb runtimes instead of the flat 110min/24fps
    # assumption above — that assumption inflated bpppf for any movie whose
    # real length differs a lot from 110min, which is exactly what made MHD's
    # estimated range (0.07-0.13) fit entirely inside BluRay's (contributing
    # nothing). With real runtimes: MHD min/median/max = 0.069/0.101/0.151;
    # BluRay's own p25/median/p75 = 0.116/0.128/0.191 (and legitimately much
    # higher for large premium re-encodes) — real separation, not just an
    # artifact of the duration estimate.
    "MHD": (0.065, 0.155),
    "WEB-DL": (0.041, 0.130),
    "WEBRIP": (0.050, 0.090),     # calibration's WEBRIP p25==p50==p75==0.062; widened slightly, still tight
    "HDTV": (0.086, 0.239),
}
# MHD's calibration samples were small (8 and 25) — give it a gentler
# falloff than the rest so a handful of outliers can't tank it to zero.
_BPPF_TAIL_OVERRIDE = {"MHD": 0.7}


def bitrate_normalization_signal(profile: dict) -> list[Evidence]:
    bpppf = profile["normalization"].get("bits_per_pixel_per_frame")
    if bpppf is None:
        return []
    contrib = _zero()
    for cand, (lo, hi) in _BPPF_RANGES.items():
        contrib[cand] = _range_score(bpppf, lo, hi, peak=14.0, tail=_BPPF_TAIL_OVERRIDE.get(cand, 0.55))
    return [Evidence(
        feature="bits_per_pixel_per_frame", value=round(bpppf, 4),
        contributions=contrib,
        strength="medium", reliability=0.5,
        explanation=(f"Bitrate de vídeo normalizado a {bpppf:.3f} bits/píxel/frame, comparado contra el rango "
                     "típico de cada tier a esta resolución y framerate (calibrado con archivos reales), no contra "
                     "un umbral fijo de Mbps. Los rangos se solapan bastante entre tiers, así que esta señal por sí "
                     "sola no decide: se combina con el resto."),
    )]


def video_share_signal(profile: dict) -> list[Evidence]:
    """A file can be large purely from several lossless audio tracks — this
    checks the video's own SHARE of the total bitrate isn't being inflated by
    that, complementing (not replacing) the bpppf signal above."""
    share = profile["normalization"].get("video_share_of_file")
    if share is None:
        return []
    if share < 0.55:
        return [Evidence(
            feature="video_share_of_file", value=round(share, 2),
            contributions=_c(**{"BDRemux": -8, "BluRay": -3}),
            strength="weak", reliability=0.5,
            explanation=f"El vídeo es solo el {share*100:.0f}% del bitrate total, el tamaño del archivo puede estar inflado por el audio, no por un vídeo de bitrate real alto.",
        )]
    return []


# ---------------------------------------------------------------------------
# Audio (spec sections 9, 27 — no single codec decides anything alone)
# ---------------------------------------------------------------------------

def audio_profile_signal(profile: dict) -> list[Evidence]:
    tracks = profile["audio_tracks"]
    if not tracks:
        return []
    ev: list[Evidence] = []
    lossless_n = sum(1 for t in tracks if t.get("lossless"))
    premium_n = sum(1 for t in tracks if t.get("atmos") or t.get("dts_x"))
    lossy_codecs = {(t.get("codec") or "").lower() for t in tracks if not t.get("lossless")}

    if lossless_n:
        ev.append(Evidence(
            feature="lossless_audio_tracks", value=lossless_n,
            contributions=_c(BDRemux=16, BluRay=10, MHD=2, **{"WEB-DL": -10, "WEBRIP": -12, "HDTV": -18, "SD": -18}),
            strength="medium", reliability=0.75,
            explanation=f"{lossless_n} pista(s) de audio sin pérdida (TrueHD/DTS-HD MA/FLAC/PCM) son casi siempre de origen disco, nunca de streaming.",
        ))
    if premium_n:
        ev.append(Evidence(
            feature="premium_object_audio", value=premium_n,
            contributions=_c(BDRemux=8, BluRay=5, **{"WEB-DL": 5}),
            strength="weak", reliability=0.5,
            explanation="Atmos/DTS:X aparece tanto en discos UHD como en algunos WEB-DL premium, orienta hacia fuentes de gama alta sin decidir entre ellas.",
        ))
    if any(c in lossy_codecs for c in ("e-ac-3", "eac3", "dd+", "ddp")):
        ev.append(Evidence(
            feature="eac3_ddplus_audio", value=True,
            contributions=_c(**{"WEB-DL": 7, "WEBRIP": 5}, BluRay=1),
            strength="weak", reliability=0.45,
            explanation="E-AC-3/DD+ es habitual en streaming, pero también aparece remultiplexado desde disco: señal débil por sí sola.",
        ))
    if any(c in lossy_codecs for c in ("mpeg audio", "mp2", "ac-3")) and profile["video"].get("height", 0) and profile["video"]["height"] <= 576:
        ev.append(Evidence(
            feature="broadcast_audio_at_sd", value=True,
            contributions=_c(HDTV=6, SD=6),
            strength="weak", reliability=0.4,
            explanation="Audio MPEG/AC-3 simple a resolución SD es compatible con emisión de TV o DVD.",
        ))
    return ev


def subtitle_language_breadth_signal(profile: dict) -> list[Evidence]:
    """Weak signal added after calibration against ~1300 real library files
    (2026-07): big platforms tend to bundle subtitles for many regions in
    their own WEB-DL master (median ~4-7 languages in that sample), while
    disc/broadcast releases typically carry just 1-3 (or none for HDTV).
    Confirmed weak on its own (medians overlap between WEB-DL and WEBRip),
    kept at "weak" strength on purpose — a nudge, not a decision."""
    subs = profile["subtitle_tracks"]
    languages = {t.get("language") for t in subs if t.get("language") and t.get("language") != "und"}
    n = len(languages) or len(subs)
    if n >= 6:
        return [Evidence(
            feature="subtitle_language_breadth", value=n,
            contributions=_c(**{"WEB-DL": 4, "WEBRIP": 2}, MHD=2, **{"BluRay": -2, "HDTV": -3}),
            strength="weak", reliability=0.35,
            explanation=f"{n} idiomas de subtítulos, las plataformas grandes suelen empaquetar muchas regiones en su propio WEB-DL.",
        )]
    if n <= 1 and subs:
        return [Evidence(
            feature="subtitle_language_breadth", value=n,
            contributions=_c(BluRay=2, HDTV=2, **{"WEB-DL": -2}),
            strength="weak", reliability=0.3,
            explanation="Solo 1 idioma de subtítulos, más típico de un disco o una emisión que de un WEB-DL de plataforma grande.",
        )]
    return []


def subtitle_profile_signal(profile: dict) -> list[Evidence]:
    subs = profile["subtitle_tracks"]
    if not subs:
        return []
    ev: list[Evidence] = []
    pgs_n = profile["topology"].get("pgs_count", 0)
    vobsub_n = profile["topology"].get("vobsub_count", 0)
    text_n = profile["topology"].get("text_subtitle_count", 0)

    if pgs_n:
        # BluRay used to get more than double MHD's credit here (7 vs 3, no
        # calibration data behind the split — MHD had no per-evidence-type
        # validation, only its overall bpppf range did). No technical reason
        # supports that gap: an MHD re-encode keeps the disc's original PGS
        # track just as readily as a "regular" BluRay re-encode does (subs
        # are tiny, re-encoders rarely bother re-authoring them regardless of
        # how aggressively they compress the video) — confirmed as the sole
        # driver of a real misclassification (Chappie, 2026-07-28): PGS
        # alone explained the entire BluRay-over-MHD margin. Narrowed so it
        # still favors BluRay somewhat (full-quality encoders are marginally
        # likelier to leave premium subtitle formats untouched than the most
        # size-conscious MHD groups) without dominating the decision.
        ev.append(Evidence(
            feature="pgs_subtitles", value=pgs_n,
            contributions=_c(BDRemux=9, BluRay=6, MHD=5, **{"WEB-DL": -4, "WEBRIP": -4}),
            strength="medium", reliability=0.7,
            explanation=f"{pgs_n} pista(s) PGS (subtítulo de imagen HDMV) son compatibles con un origen Blu-ray, no concluyentes en solitario.",
        ))
    if vobsub_n:
        ev.append(Evidence(
            feature="vobsub_subtitles", value=vobsub_n,
            contributions=_c(SD=10, FDVD=6, **{"BDRemux": -6, "WEB-DL": -6}),
            strength="medium", reliability=0.7,
            explanation=f"{vobsub_n} pista(s) VobSub son el formato de subtítulo de imagen propio de DVD.",
        ))
    if text_n and not pgs_n and not vobsub_n:
        ev.append(Evidence(
            feature="text_only_subtitles", value=text_n,
            contributions=_c(**{"WEB-DL": 5, "WEBRIP": 5, "HDTV": 2}),
            strength="weak", reliability=0.4,
            explanation="Solo subtítulos de texto (sin PGS/VobSub) es más habitual en rips web que en discos.",
        ))
    return ev


# ---------------------------------------------------------------------------
# Re-encode / transcode signals (from transcode.py)
# ---------------------------------------------------------------------------

def transcode_signal(profile: dict, signals) -> list[Evidence]:
    p = signals.video_transcode_probability
    explanation = "; ".join(signals.notes) or "Señales de recodificación evaluadas sobre el propio stream."

    if signals.has_encoder_fingerprint:
        # Calibrated (2026-07, ~1300 real library files): a bare x264/x265
        # settings string is genuinely ambiguous for WEB-DL specifically —
        # several streaming platforms' own masters carry the exact same
        # fingerprint as a scene re-encode. This was first found for
        # single-pass CRF; a second pass (same library) then caught a
        # CONFIRMED genuine Netflix WEB-DL (Sirens S01, "NF" platform tag)
        # reporting `rc=2pass` in its own settings dump — so two-pass isn't
        # a reliable tell either, and no longer gets special strong-penalty
        # treatment (an earlier version of this code did, and measurably
        # regressed accuracy on this exact dataset once corrected to detect
        # x264's real "Npass" format instead of a "pass=N" pattern that
        # never actually matched anything).
        #
        # It is NOT ambiguous for BDRemux/FBD, though: those are a
        # byte-for-byte copy of the disc's own video stream, and commercial
        # Blu-ray discs are mastered with proprietary/hardware encoders,
        # never with an open-source x264/x265 CLI dump — so any such
        # fingerprint at all is real (if not overwhelming) evidence against
        # them, unlike the platform-encode ambiguity that applies to WEB-DL.
        # BluRay/MHD get the SAME weight here (both are re-encodes by
        # definition — this signal can't and shouldn't discriminate between
        # re-encode tiers, only "re-encoded at all" vs "genuinely untouched
        # source"). An earlier version favored BluRay over MHD (4x vs 3x)
        # with no justification; narrowed alongside pgs_subtitles above
        # after both together fully explained a real misclassification
        # (Chappie, 2026-07-28).
        ev = [Evidence(
            feature="video_transcode_probability", value=round(p, 2),
            contributions=_c(BDRemux=-12 * p, **{"FBD": -6 * p}, BluRay=4 * p, MHD=4 * p,
                              WEBRIP=4 * p, **{"WEB-DL": -3 * p}),
            strength="weak", reliability=0.3, explanation=explanation,
        )]
        # Unlike WEB-DL above, a hand-encoder fingerprint is NOT ambiguous
        # for BDRemux/FBD: those are supposed to be a byte-for-byte copy of
        # the disc's own video stream, and commercial Blu-ray/DVD discs are
        # authored with proprietary/hardware encoders — never an open-source
        # x264/x265 CLI dump. So this fingerprint alone is strong, near-
        # decisive evidence the stream was actually re-encoded, no matter how
        # close the bitrate otherwise looks to a genuine remux (confirmed in
        # production: a file with "BDRemux" in its own name and an x264
        # fingerprint, whose bitrate still scored in-range, kept winning
        # BDRemux because the weak evidence above wasn't enough to overrule
        # it on its own). A separate, stronger entry — rather than raising
        # the weak one above — keeps the WEB-DL calibration untouched.
        ev.append(Evidence(
            feature="disc_tier_encoder_fingerprint", value=1.0,
            contributions=_c(BDRemux=-30, FBD=-20),
            strength="strong", reliability=0.75,
            explanation=(f"Huella de encoder de mano ({signals.encoder_name or 'x264/x265'}) detectada: "
                         "un remux o disco completo genuino no debería llevarla nunca, así que descarta con "
                         "fuerza que sea un remux real, con independencia de lo cerca que esté el bitrate."),
        ))
        if signals.fast_effort_preset_signature:
            # A bare fingerprint (CRF or two-pass, any bitrate) is ambiguous
            # for WEB-DL specifically — see the weak entry above and
            # TranscodeSignals' own docstring. This is NOT: ref<=1 and
            # subme<=2 is x264's "veryfast"-or-faster preset tier, verified
            # against the calibration dataset's own confirmed genuine "NF
            # WEB-DL" release (Sirens S01) — which uses ref=3-4/subme=10
            # throughout, including its own 2-pass-with-bitrate episodes, so
            # this isn't just "any fast rate-control mode" either. No
            # streaming platform or disc author has a reason to trade away
            # quality for encode speed; a fast/low-effort preset is a scene/
            # group re-encode's signature, so it rules out WEB-DL (and
            # BDRemux/FBD, already ruled out above by the bare fingerprint)
            # just as hard as the disc-tier check does. Real case (Los
            # Tudor S02, 2026-07-30): ref=1/subme=2 tied WEB-DL with WEBRIP
            # before this.
            ev.append(Evidence(
                feature="fast_effort_preset_signature", value=1.0,
                contributions=_c(**{"WEB-DL": -30}),
                strength="strong", reliability=0.7,
                explanation="Perfil de codificación rápido/de bajo esfuerzo (equivalente a 'veryfast' o más "
                            "rápido de x264): ninguna plataforma de streaming codifica así para entregar "
                            "contenido, así que descarta con fuerza que sea un WEB-DL genuino.",
            ))
    else:
        # No fingerprint at all is still a fairly strong "untouched" signal —
        # calibration didn't contradict this case (it's rare in the dataset,
        # most files there do carry a libx264/libx265 fingerprint one way
        # or another), so it keeps its original weight.
        ev = [Evidence(
            feature="video_transcode_probability", value=round(p, 2),
            contributions=_c(BDRemux=-15 * p, **{"WEB-DL": 20 * p}, WEBRIP=-10 * p, BluRay=-5 * p, MHD=-5 * p),
            strength="strong", reliability=0.6, explanation=explanation,
        )]

    if signals.screen_capture_probability > 0:
        ev.append(Evidence(
            feature="screen_capture_probability", value=round(signals.screen_capture_probability, 2),
            contributions=_c(WEBRIP=8),
            strength="weak", reliability=0.4,
            explanation="Redimensionado sin huella de encoder: leve indicio de una captura de pantalla en vez de un rip directo.",
        ))
    return ev


# ---------------------------------------------------------------------------
# Bitstream sampling (spec section 13) — optional, only when it completed.
# ---------------------------------------------------------------------------

def sampling_signal(sample_result) -> list[Evidence]:
    if not sample_result or not sample_result.any_ok:
        return []
    ok_windows = [w for w in sample_result.windows if w.ok]
    bitrates = [w.local_bitrate_bps for w in ok_windows if w.local_bitrate_bps]
    ev: list[Evidence] = []
    if len(bitrates) >= 2:
        mean = sum(bitrates) / len(bitrates)
        variance = sum((b - mean) ** 2 for b in bitrates) / len(bitrates)
        cv = (variance ** 0.5 / mean) if mean else 0.0
        if cv > 0.35:
            ev.append(Evidence(
                feature="sampled_bitrate_variability", value=round(cv, 2),
                contributions=_c(BDRemux=6, BluRay=4, **{"WEB-DL": 2}),
                strength="weak", reliability=0.45 * sample_result.coverage,
                explanation=f"Variabilidad de bitrate entre muestras alta (CV={cv:.2f}), más propio de un stream VBR sin recomprimir.",
            ))
        elif cv < 0.12:
            ev.append(Evidence(
                feature="sampled_bitrate_variability", value=round(cv, 2),
                contributions=_c(**{"WEB-DL": 4, "WEBRIP": 4, "HDTV": 3}),
                strength="weak", reliability=0.4 * sample_result.coverage,
                explanation=f"Bitrate muy uniforme entre muestras (CV={cv:.2f}), compatible con un encode a bitrate objetivo (CBR/VBR acotado).",
            ))

    gop_lengths = [g for w in ok_windows for g in w.gop_lengths]
    if gop_lengths:
        avg_gop = sum(gop_lengths) / len(gop_lengths)
        if avg_gop >= 100:
            ev.append(Evidence(
                feature="sampled_gop_length", value=round(avg_gop, 1),
                contributions=_c(BDRemux=5, BluRay=3),
                strength="weak", reliability=0.4 * sample_result.coverage,
                explanation=f"GOP muestreado largo (~{avg_gop:.0f} frames), encaja con un stream de disco sin recomprimir para streaming adaptativo.",
            ))
        elif avg_gop <= 60:
            ev.append(Evidence(
                feature="sampled_gop_length", value=round(avg_gop, 1),
                contributions=_c(**{"WEB-DL": 3, "WEBRIP": 3, "HDTV": 2}),
                strength="weak", reliability=0.35 * sample_result.coverage,
                explanation=f"GOP muestreado corto (~{avg_gop:.0f} frames), típico de un encode pensado para streaming/seek rápido.",
            ))
    return ev


def collect_all_evidence(profile: dict, transcode_signals, sample_result) -> list[Evidence]:
    detectors = [
        structural_single_file(profile),
        container_format(profile),
        container_fragmentation(profile),
        chapters_signal(profile),
        resolution_signal(profile),
        scan_type_signal(profile),
        hdr_dv_signal(profile),
        video_codec_signal(profile),
        bluray_compat_flag(profile),
        bitrate_normalization_signal(profile),
        video_share_signal(profile),
        audio_profile_signal(profile),
        subtitle_profile_signal(profile),
        subtitle_language_breadth_signal(profile),
        transcode_signal(profile, transcode_signals),
        sampling_signal(sample_result),
    ]
    return [e for group in detectors for e in group]
