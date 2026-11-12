"""Krossvord setkasini yasaydi (so'zlarni kesishtirib joylashtiradi)."""


def _can_place(cells, dirs, word, r, c, dr, dc, limit):
    if (r - dr, c - dc) in cells or (r + dr * len(word), c + dc * len(word)) in cells:
        return -1
    cross = 0
    for i, ch in enumerate(word):
        p = (r + dr * i, c + dc * i)
        if p in cells:
            if cells[p] != ch or (dr, dc) in dirs[p]:
                return -1
            cross += 1
        else:
            if (p[0] + dc, p[1] + dr) in cells or (p[0] - dc, p[1] - dr) in cells:
                return -1
    rows = [p[0] for p in cells] + [r, r + dr * (len(word) - 1)]
    cols = [p[1] for p in cells] + [c, c + dc * (len(word) - 1)]
    if max(rows) - min(rows) + 1 > limit or max(cols) - min(cols) + 1 > limit:
        return -1
    return cross


def build_grid(items, want, limit=18):
    """items: [{'word','clue'}]. Natija: dict(rows, cols, cells, nums, across, down)."""
    items = sorted(items, key=lambda x: -len(x["word"]))
    cells, dirs, placed = {}, {}, []

    def put(it, r, c, dr, dc):
        for i, ch in enumerate(it["word"]):
            p = (r + dr * i, c + dc * i)
            cells[p] = ch
            dirs.setdefault(p, set()).add((dr, dc))
        placed.append((it, r, c, dr, dc))

    first = items[0]
    put(first, 0, 0, 0, 1)
    for it in items[1:]:
        if len(placed) >= want:
            break
        best = None
        for p, ch in list(cells.items()):
            for j, wc in enumerate(it["word"]):
                if wc != ch:
                    continue
                for dr, dc in ((1, 0), (0, 1)):
                    if (dr, dc) in dirs[p]:
                        continue
                    r, c = p[0] - dr * j, p[1] - dc * j
                    sc = _can_place(cells, dirs, it["word"], r, c, dr, dc, limit)
                    if sc >= 1 and (best is None or sc > best[0]):
                        best = (sc, r, c, dr, dc)
        if best:
            put(it, *best[1:])
    r0 = min(p[0] for p in cells)
    c0 = min(p[1] for p in cells)
    cells = {(r - r0, c - c0): ch for (r, c), ch in cells.items()}
    starts = {}
    for it, r, c, dr, dc in placed:
        starts.setdefault((r - r0, c - c0), []).append((it, (dr, dc)))
    nums, across, down, n = {}, [], [], 0
    for r in range(max(p[0] for p in cells) + 1):
        for c in range(max(p[1] for p in cells) + 1):
            if (r, c) in starts:
                n += 1
                nums[(r, c)] = n
                for it, d in starts[(r, c)]:
                    (across if d == (0, 1) else down).append((n, it["clue"], it["word"]))
    return dict(rows=max(p[0] for p in cells) + 1, cols=max(p[1] for p in cells) + 1,
                cells=cells, nums=nums, across=across, down=down, count=len(placed))
