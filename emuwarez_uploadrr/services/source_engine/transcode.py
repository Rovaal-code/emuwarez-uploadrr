"""Lightweight re-encode/transcode signals — spec section 14.

Deliberately shallow: only fast, explainable checks (encoder identity string,
CRF/two-pass/target-bitrate markers inside `Encoded_Library_Settings`, coded
vs. display dimension mismatch beyond ordinary macroblock padding). No frame
decoding here — that's `sampling.py`'s job, and its GOP-regularity result is
folded in by the caller when available.

Absence of a hand-encoder fingerprint is NOT proof the stream is untouched
(a build without the settings string, or a settings string stripped during
remux, would look identical) — `video_stream_untouched_probability` reflects
that asymmetry: it's never pushed to 100%, only ever brought down from it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_REENCODE_LIBS = ("x264", "x265", "x266", "svt-av1", "aomenc", "rav1e", "libvpx")
_CRF_RE = re.compile(r"\bcrf=([\d.]+)", re.I)
_BITRATE_RE = re.compile(r"\bbitrate=(\d+)", re.I)
# x264's own settings dump reports its rate-control mode as "rc=2pass" (also
# seen as "rc=1pass") — NOT "pass=2", which was this regex's original (and
# wrong) assumption; it never matched a real x264 two-pass encode. Catch
# both that real form and the "pass=N" form some other tools/dumps use.
_PASS_RE = re.compile(r"\b(\d)[-\s]?pass\b|\bpass=(\d)\b", re.I)
_KEYINT_RE = re.compile(r"\bkeyint=(\d+)", re.I)
_REF_RE = re.compile(r"\bref=(\d+)", re.I)
_SUBME_RE = re.compile(r"\bsubme=(\d+)", re.I)


@dataclass
class TranscodeSignals:
    has_encoder_fingerprint: bool
    encoder_name: str | None
    crf: float | None
    target_bitrate_bps: int | None
    two_pass: bool | None
    keyint: int | None
    resize_evidence: bool
    crop_evidence: bool
    video_transcode_probability: float
    video_stream_untouched_probability: float
    screen_capture_probability: float
    # x264's "veryfast"-or-faster preset tier (ref<=1 AND subme<=2 — matches
    # ultrafast/superfast/veryfast's own defaults, verified against x264's
    # published preset table). Unlike CRF-vs-two-pass (checked and found NOT
    # reliable — see below), this genuinely never shows up on a real
    # streaming platform's own delivery encode or a disc author's master:
    # both use a slow/high-quality preset even when they do target a fixed
    # bitrate (a confirmed genuine "NF WEB-DL" release in this engine's
    # calibration dataset, Sirens S01, uses ref=3-4/subme=10 throughout,
    # including its own 2-pass-with-bitrate episodes). A fast/low-effort
    # preset is a scene/group re-encode workflow — nobody re-encodes at
    # "veryfast" for quality, only for speed, which a platform's own
    # pipeline or a disc's own hardware encoder has no reason to do.
    # Real case (Los Tudor S02, 2026-07-30): ref=1/subme=2/trellis=0/
    # 8x8dct=0/me=hex (x264 veryfast's exact defaults) tied WEB-DL with
    # WEBRIP even though a legitimate WEB-DL/BDRemux structurally can't be a
    # fast/low-effort re-encode.
    fast_effort_preset_signature: bool
    notes: list[str] = field(default_factory=list)


def analyze_transcode_signals(video: dict) -> TranscodeSignals:
    settings = video.get("encoder_settings") or ""
    encoder = (video.get("encoder") or video.get("writing_library") or "")
    encoder_l = encoder.lower()

    has_fingerprint = bool(settings) or any(tag in encoder_l for tag in _REENCODE_LIBS)
    notes: list[str] = []

    crf_m = _CRF_RE.search(settings)
    crf = float(crf_m.group(1)) if crf_m else None
    bitrate_m = _BITRATE_RE.search(settings)
    target_bitrate = int(bitrate_m.group(1)) * 1000 if bitrate_m else None
    pass_m = _PASS_RE.search(settings)
    two_pass = ((pass_m.group(1) or pass_m.group(2)) == "2") if pass_m else None
    keyint_m = _KEYINT_RE.search(settings)
    keyint = int(keyint_m.group(1)) if keyint_m else None
    ref_m = _REF_RE.search(settings)
    ref = int(ref_m.group(1)) if ref_m else None
    subme_m = _SUBME_RE.search(settings)
    subme = int(subme_m.group(1)) if subme_m else None
    fast_preset = ref is not None and subme is not None and ref <= 1 and subme <= 2

    coded_w, coded_h = video.get("coded_width"), video.get("coded_height")
    disp_w, disp_h = video.get("width"), video.get("height")
    resize_evidence = False
    if coded_w and disp_w and coded_h and disp_h:
        # A little slack for the standard 16px macroblock padding on height
        # (e.g. 1080 -> stored 1088) — anything beyond that is an actual resize.
        pad_w = abs(coded_w - disp_w)
        pad_h = abs(coded_h - disp_h)
        resize_evidence = pad_w > 0 or pad_h > 16

    crop_evidence = False
    if disp_w and disp_h and disp_h > 0:
        ratio = disp_w / disp_h
        # Common cinematic crops (2.35-2.40:1) inside an otherwise 16:9
        # coded frame — informational, doesn't by itself imply re-encode.
        crop_evidence = 2.3 <= ratio <= 2.45

    if has_fingerprint:
        # Calibrated against 1300+ real, name-labeled library files (2026-07):
        # a plain x264/x265 settings string — even with a CRF value — is
        # NOT reliable evidence of a hand/scene re-encode. Several major
        # streaming platforms' own delivery pipelines run libx264/libx265
        # internally and leave an identical-looking settings dump (CRF,
        # single-pass rc=crf included) on their OWN original WEB-DL masters.
        # Before calibration this alone pushed WEB-DL's transcode
        # probability to 0.95, which misclassified the large majority of
        # real WEB-DL files in that dataset as WEBRip/BluRay. Two-pass was
        # initially treated as a much stronger tell (streaming platforms
        # supposedly using single-pass CRF/VBR only) until a confirmed
        # genuine Netflix WEB-DL turned up reporting `rc=2pass` in its own
        # dump — so two-pass gets no special weight either now.
        video_transcode_p = 0.45 if settings else 0.35
        notes.append(f"Encoder de mano detectado ({encoder or 'desconocido'})" +
                      (f", CRF {crf}" if crf is not None else "") +
                      (", two-pass" if two_pass else "") +
                      ", por sí solo no distingue un WEB-DL genuino de un re-encode (varias "
                      "plataformas de streaming usan x264/x265 internamente, con o sin two-pass)")
        if fast_preset:
            # Unlike a bare fingerprint, this DOES distinguish — see the
            # dataclass field's own comment for the full rationale.
            video_transcode_p = 0.85
            notes.append(
                f"Perfil de codificación rápido/de bajo esfuerzo (ref={ref}, subme={subme}, "
                "equivalente al preset 'veryfast' o más rápido de x264) — ninguna plataforma de "
                "streaming ni disco original codifica así, es propio de un re-encode rápido de grupo/escena."
            )
    else:
        video_transcode_p = 0.15
        notes.append("Sin huella de encoder de mano en los metadatos (no concluyente por sí solo)")

    # Never fully confident either way — see module docstring.
    untouched_p = max(0.05, min(0.85, 1.0 - video_transcode_p))

    screen_capture_p = 0.0
    if resize_evidence and not has_fingerprint:
        # A resize with no encoder fingerprint at all is unusual for a normal
        # re-encode pipeline and mildly suggests a capture tool instead.
        screen_capture_p = 0.2
        notes.append("Redimensionado sin huella de encoder, señal débil de captura")

    return TranscodeSignals(
        has_encoder_fingerprint=has_fingerprint,
        encoder_name=encoder or None,
        crf=crf, target_bitrate_bps=target_bitrate, two_pass=two_pass, keyint=keyint,
        resize_evidence=resize_evidence, crop_evidence=crop_evidence,
        fast_effort_preset_signature=fast_preset,
        video_transcode_probability=video_transcode_p,
        video_stream_untouched_probability=untouched_p,
        screen_capture_probability=screen_capture_p,
        notes=notes,
    )
