# SPDX-License-Identifier: MIT
"""Audio handling with loudness normalization for PA Simulator."""

import os
import tempfile
import time
import atexit
import pygame.mixer as mixer
import soundfile as sf
import pyloudnorm as pyln
from typing import Optional

from constants import TARGET_LOUDNESS, AUDIO_FADE_MS

# Create a temp directory for audio files
_temp_dir = tempfile.mkdtemp(prefix="pa_simulator_audio_")
# Two double-buffered temp files for PA (mixer.music) + a third for STA
# (mixer.Sound on a dedicated channel). PA double-buffers to dodge file
# locks; STA loads fully into memory at Sound() construction so a single
# file is enough — the next write overwrites freely.
_temp_file_paths = [
    os.path.join(_temp_dir, "temp_audio_1.mp3"),
    os.path.join(_temp_dir, "temp_audio_2.mp3"),
    os.path.join(_temp_dir, "temp_sta.mp3"),
]
_STA_TEMP_INDEX = 2


def _cleanup_temp_dir():
    """Clean up the temp directory on exit."""
    global _temp_file_paths, _temp_dir
    try:
        for path in _temp_file_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    # File might be in use, skip it
                    pass
        if os.path.exists(_temp_dir):
            try:
                os.rmdir(_temp_dir)
            except OSError:
                # Directory not empty, skip it
                pass
    except Exception:
        pass


# Register cleanup on exit
atexit.register(_cleanup_temp_dir)


class AudioPlayer:
    """Handles PA announcements and departure melodies with loudness normalization."""

    def __init__(self, audio_root: str, stops: list):
        """Initialize the audio player.

        Args:
            audio_root: Base directory containing pa/ and sta/ folders. Callers
                resolve this via ``route_loader.resolve_audio_root`` — it is the
                route's own folder unless route.json declares ``audio_root``
                (per-line shared pool). Never search more than this one root.
            stops: List of station data from route.json
        """
        self.pa_dir = os.path.join(audio_root, "pa")
        self.sta_dir = os.path.join(audio_root, "sta")
        self.stops = stops
        self._temp_index = 0  # Track which temp file to use next
        # Last-played track metadata for position()/duration() — used by the
        # tutorial's seek bar and any future progress UI. Set in _load_and_play
        # right before mixer.music.play(); zeroed on init so position() returns
        # None safely before any track has played.
        self._current_duration: float = 0.0
        self._current_start_offset: float = 0.0

        # Initialize mixer if not already done
        if not mixer.get_init():
            mixer.init()

        # PA flows through mixer.music (single global stream). STA flows
        # through a dedicated mixer.Channel + Sound so it can overlap PA —
        # IRL the platform departure melody and the in-train PA come from
        # different audio sources. _sta_sound is held to keep the Sound
        # alive for the channel's lifetime; pygame stops playback if the
        # Sound is GC'd mid-play.
        # Reserve channel 0 so any future Sound.play() without an explicit
        # channel can't steal it from STA.
        mixer.set_reserved(1)
        self._sta_channel = mixer.Channel(0)
        self._sta_sound: Optional[mixer.Sound] = None
        # pygame.Channel.get_busy() returns True even on a paused channel,
        # so we track pause state explicitly. Used by is_sta_playing() so
        # _next_sta treats "paused" as "not playing" (Page Up after End
        # plays from start, not restart-from-sta_cut).
        self._sta_paused: bool = False
        # Wall-clock progress tracking for STA — mixer.Channel has no
        # get_pos() equivalent of mixer.music's, so position() / duration()
        # fall back to time.monotonic() arithmetic when STA is the active
        # stream. Drifts during pause; tutorial seek bar hides during pause
        # (is_sta_playing() returns False), so the drift is invisible.
        self._sta_play_start_ts: Optional[float] = None
        self._sta_duration_s: float = 0.0

    def play_pa(self, stop_index: int, pa_index: int) -> None:
        """Load and play PA announcement with loudness normalization.

        Args:
            stop_index: Index of the current stop
            pa_index: Index of the PA track within the stop
        """
        try:
            pa_tracks = self.stops[stop_index].get("pa", [])
            if not pa_tracks or pa_index >= len(pa_tracks):
                return

            track_name = pa_tracks[pa_index]
            if not track_name:
                return

            track_path = os.path.join(self.pa_dir, track_name + ".mp3")
            self._load_and_play(track_path)
        except (IndexError, KeyError) as e:
            print(f"PA playback error: {e}")

    def play_pa_at_station(self, stop_index: int, idx: int) -> None:
        """Load and play an at-station PA track.

        Mirrors play_pa but reads from stop['pa_at_station']. Both lists share
        the pa/ folder (slugs resolve to pa/<slug>.mp3).
        """
        try:
            tracks = self.stops[stop_index].get("pa_at_station", [])
            if not tracks or idx >= len(tracks):
                return

            track_name = tracks[idx]
            if not track_name:
                return

            track_path = os.path.join(self.pa_dir, track_name + ".mp3")
            self._load_and_play(track_path)
        except (IndexError, KeyError) as e:
            print(f"PA-at-station playback error: {e}")

    def play_sta(self, stop_index: int, sta_index: int, cut_position: float = 0) -> None:
        """Load and play departure melody (sta = station melody).

        Args:
            stop_index: Index of the current stop
            sta_index: Index of the STA track within the stop
            cut_position: Position in seconds to start playback (default 0)
        """
        try:
            sta_tracks = self.stops[stop_index].get("sta", [])
            if not sta_tracks or sta_index >= len(sta_tracks):
                return

            track_name = sta_tracks[sta_index]
            if not track_name:
                return

            track_path = os.path.join(self.sta_dir, track_name + ".mp3")
            self._load_and_play_sta(track_path, cut_position=cut_position)
        except (IndexError, KeyError) as e:
            print(f"STA playback error: {e}")

    def _load_and_play(self, track_path: str, cut_position: float = 0) -> None:
        """Internal method to normalize and play audio.

        Args:
            track_path: Path to the audio file
            cut_position: Position in seconds to start playback
        """
        if not os.path.exists(track_path):
            print(f"Audio file not found: {track_path}")
            return

        try:
            # Read audio file
            data, rate = sf.read(track_path)

            # Handle stereo/mono properly
            meter = pyln.Meter(rate)
            loudness = meter.integrated_loudness(data)

            # Normalize loudness
            normalized = pyln.normalize.loudness(data, loudness, TARGET_LOUDNESS)

            # Use double-buffering to avoid file locking issues
            # Write to the alternate buffer while the current one is playing
            self._temp_index = 1 - self._temp_index  # Toggle between 0 and 1
            write_path = _temp_file_paths[self._temp_index]

            # Write normalized audio to temp file
            sf.write(write_path, normalized, rate)

            # Load and play
            mixer.music.unload()
            mixer.music.load(write_path)

            self._current_duration = len(data) / rate
            self._current_start_offset = float(cut_position)
            if cut_position > 0:
                mixer.music.play(fade_ms=AUDIO_FADE_MS, start=cut_position)
            else:
                mixer.music.play(fade_ms=AUDIO_FADE_MS)

        except Exception as e:
            print(f"Audio playback error: {type(e).__name__}: {e}")
            # Don't toggle index on error so we can retry
            self._temp_index = 1 - self._temp_index

    def _load_and_play_sta(self, track_path: str, cut_position: float = 0) -> None:
        """STA playback path. Uses a dedicated mixer.Channel so STA can
        overlap PA (mixer.music). Sound.play() has no start-offset arg, so
        sta_cut is implemented by slicing leading samples off the
        normalized array before writing the temp file.
        """
        if not os.path.exists(track_path):
            print(f"STA file not found: {track_path}")
            return

        try:
            data, rate = sf.read(track_path)
            meter = pyln.Meter(rate)
            loudness = meter.integrated_loudness(data)
            normalized = pyln.normalize.loudness(data, loudness, TARGET_LOUDNESS)

            if cut_position > 0:
                start_sample = int(cut_position * rate)
                if 0 < start_sample < len(normalized):
                    normalized = normalized[start_sample:]

            write_path = _temp_file_paths[_STA_TEMP_INDEX]
            sf.write(write_path, normalized, rate)

            # Sound() loads the entire file into memory, so the temp file
            # is free to be overwritten on the next STA play. Channel.play
            # auto-stops the previous sound on the channel — matches the
            # restart-from-sta_cut semantic.
            self._sta_sound = mixer.Sound(write_path)
            # Unpause first in case the channel was previously paused via the
            # End-key — Channel.play on a paused channel can otherwise leave
            # the new sound stuck silent.
            self._sta_channel.unpause()
            self._sta_channel.play(self._sta_sound, fade_ms=AUDIO_FADE_MS)
            self._sta_paused = False
            self._sta_duration_s = self._sta_sound.get_length()
            self._sta_play_start_ts = time.monotonic()
        except Exception as e:
            print(f"STA playback error: {type(e).__name__}: {e}")
            # A failed fresh-play attempt invalidates any prior pause state —
            # nothing is playing, so "paused" is incoherent.
            self._sta_paused = False

    def pause(self) -> None:
        """Pause both PA and STA streams. Used by jump_to_stop /
        restore_state / tutorial state-jumps where a clean wipe is wanted.
        For the End-key (selective pause), use pause_pa() / pause_sta()."""
        mixer.music.pause()
        self._sta_channel.pause()
        self._sta_paused = True

    def pause_pa(self) -> None:
        """Pause only the PA stream (mixer.music)."""
        mixer.music.pause()

    def pause_sta(self) -> None:
        """Pause only the STA stream (dedicated channel)."""
        self._sta_channel.pause()
        self._sta_paused = True

    def unpause(self) -> None:
        """Resume both PA and STA streams."""
        mixer.music.unpause()
        self._sta_channel.unpause()
        self._sta_paused = False

    def is_playing(self) -> bool:
        """True if either PA or STA is currently playing."""
        return self.is_pa_playing() or self.is_sta_playing()

    def is_pa_playing(self) -> bool:
        """True if PA (mixer.music) is currently playing."""
        return mixer.music.get_busy()

    def is_sta_playing(self) -> bool:
        """True if STA is currently playing. A paused channel reports busy
        in pygame; the explicit ``_sta_paused`` flag excludes it."""
        return self._sta_channel.get_busy() and not self._sta_paused

    def position(self) -> Optional[float]:
        """Current playback position in seconds for whichever stream is live
        (PA preferred when both somehow play). Returns None when neither
        stream is producing audio — callers can gate UI on this directly
        without a separate is_*_playing() check."""
        if mixer.music.get_busy():
            pos_ms = mixer.music.get_pos()
            if pos_ms < 0:
                return None
            return self._current_start_offset + pos_ms / 1000.0
        if self.is_sta_playing() and self._sta_play_start_ts is not None:
            elapsed = time.monotonic() - self._sta_play_start_ts
            return min(elapsed, self._sta_duration_s)
        return None

    def duration(self) -> Optional[float]:
        """Duration in seconds for whichever stream is live (matches
        ``position()``'s stream selection). None when nothing is playing."""
        if mixer.music.get_busy() and self._current_duration > 0:
            return self._current_duration
        if self.is_sta_playing() and self._sta_duration_s > 0:
            return self._sta_duration_s
        return None

    def stop(self) -> None:
        """Stop both PA and STA streams."""
        mixer.music.stop()
        self._sta_channel.stop()
        self._sta_paused = False

    def cleanup(self) -> None:
        """Clean up resources. Caller-driven only — never tied to GC.

        Tutorial flow drops the PASimulator reference between tutorial and
        setup; if a `__del__` here called `mixer.quit()` at GC time, the
        downstream setup screen and main app would inherit a dead mixer.
        Cleanup is explicit (PASimulator.cleanup → here) on app exit only.
        """
        mixer.quit()
