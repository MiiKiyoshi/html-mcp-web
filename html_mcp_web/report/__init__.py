"""The report engine: one builder, one frame stylesheet and one pour shared by every
report skin.

A skin is a directory holding ``skin.css``, which names its faces and colours and may
restate any measure of the frame, and ``fonts/`` with the faces it embeds. The pages, the
pour of the text into two columns and every rule of the flow come from here and hold for
every skin at once.
"""

from .build import build
