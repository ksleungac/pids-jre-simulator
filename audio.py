"""Audio handling with loudness normalization for PA Simulator."""

import os
import tempfile
import atexit
import pygame.mixer as mixer
import soundfile as sf
import pyloudnorm as pyln
from typing import Optional

from constants import TARGET_LOUDNESS, AUDIO_FADE_MS

# Create a temp directory for audio files
_temp_dir = tempfile.mkdtemp(prefix="pa_simulator_audio_")
# Use two temp files for double-buffering (avoid file locking issues)
_temp_file_paths = [os.path.join(_temp_dir, "temp_audio_1.mp3"), os.path.join(_temp_dir, "temp_audio_2.mp3")]
_current_temp_index = 0


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

    def __init__(self, work_dir: str, stops: list):
        """Initialize the audio player.

        Args:
            work_dir: Base directory containing pa/ and sta/ folders
            stops: List of station data from route.json
        """
        self.pa_dir = os.path.join(work_dir, "pa")
        self.sta_dir = os.path.join(work_dir, "sta")
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
            self._load_and_play(track_path, cut_position=cut_position)
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

    def pause(self) -> None:
        """Pause current playback."""
        mixer.music.pause()

    def unpause(self) -> None:
        """Resume paused playback."""
        mixer.music.unpause()

    def is_playing(self) -> bool:
        """Check if audio is currently playing.

        Returns:
            True if audio is playing, False otherwise
        """
        return mixer.music.get_busy()

    def position(self) -> Optional[float]:
        """Current playback position in file-time seconds, or None when not
        playing. Includes any ``cut_position`` offset so the value reads as
        absolute file time even when an STA was restarted mid-play at
        sta_cut. Returns None outside playback so callers can gate UI on it
        directly without a separate is_playing() check."""
        if not mixer.music.get_busy():
            return None
        pos_ms = mixer.music.get_pos()
        if pos_ms < 0:
            return None
        return self._current_start_offset + pos_ms / 1000.0

    def duration(self) -> Optional[float]:
        """Duration of the last-loaded track in seconds, or None if no track
        has played yet."""
        return self._current_duration if self._current_duration > 0 else None

    def stop(self) -> None:
        """Stop current playback."""
        mixer.music.stop()

    def cleanup(self) -> None:
        """Clean up resources. Caller-driven only — never tied to GC.

        Tutorial flow drops the PASimulator reference between tutorial and
        setup; if a `__del__` here called `mixer.quit()` at GC time, the
        downstream setup screen and main app would inherit a dead mixer.
        Cleanup is explicit (PASimulator.cleanup → here) on app exit only.
        """
        mixer.quit()
