from __future__ import annotations

from ..logic.commands import Commands
from ..logic.faders import FaderTable
from ..mcu.surface import Surface
from ..mcu.transport import RtMidiTransport
from .app import create_server


def build() -> tuple[Commands, Surface]:
    surface = Surface(RtMidiTransport())
    return Commands(surface, FaderTable.load()), surface


def main() -> None:
    commands, _surface = build()
    create_server(commands, start_surface=True).run()


if __name__ == "__main__":
    main()
