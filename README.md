# Circular Arc Between Nodes

An Inkscape extension that replaces part of a path with one true circular arc: an SVG `A` segment, not a Bezier approximation.

Menu: **Extensions > Map's Edge Tools > General > Paths > Circular Arc Between Nodes** (extension ID `maps_edge.circular_arc_nodes`). It is also a button on the [Map's Edge Tool Panel](https://github.com/theRoadLessOrdinary/maps-edge-panel).

## Using it

1. Switch to the Node tool (N).
2. Select two or more nodes on one path.
3. Run **Circular Arc Between Nodes**.

Only the first and last selected nodes, in path order, are used. Everything between them, including any nodes, becomes one arc.

**How the bulge is chosen.** Two end points fit any number of circles, so the neighboring segment decides:

- The arc leaves the first end node in the same direction the segment before it arrives, so there is no corner at that join.
- If there is no segment before the first end node, the segment after the last end node sets the direction instead.
- If the selection spans the whole path, the existing curve's own direction at the first end node is used.

**At the other end**, if that node is a smooth node, the handle on the far side is rotated to line up with the arc. Its length is kept.

**Scaled groups.** The arc is a true circle on the canvas even when the path sits inside groups that scale it unevenly: the `A` segment is written as the ellipse that those transforms turn back into a circle.

It has no dialog, so it runs the moment it is picked and can be bound to a key in **Edit > Preferences > Interface > Keyboard Shortcuts** (search for its name).

## Requirements

- Inkscape 1.x (developed and used on Inkscape 1.4.4, Flatpak, on Linux; other platforms have not been tried)

## Install

Copy the files in this repository into a folder of their own inside Inkscape's user extensions directory, then restart Inkscape. To find that directory, open **Edit > Preferences > System** and look at **User extensions**. Typical locations:

| Install type | User extensions folder |
|---|---|
| Linux (native) | `~/.config/inkscape/extensions/` |
| Linux (Flatpak) | `~/.var/app/org.inkscape.Inkscape/config/inkscape/extensions/` |
| macOS | `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/` |
| Windows | `%APPDATA%\inkscape\extensions\` |

For example, on native Linux:

```bash
git clone https://github.com/theRoadLessOrdinary/circular-arc-nodes.git \
    ~/.config/inkscape/extensions/circular-arc-nodes
```

To uninstall, delete the folder and restart Inkscape.
