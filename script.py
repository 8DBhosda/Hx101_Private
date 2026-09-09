from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
import requests


REPORT_ID = 331
BASE_URL = "https://webnodejs.investorgain.com/cloud/v2/report/data-read/331"

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def get_financial_year(today: date) -> str:
    """Return Indian financial year, e.g. 2026-27."""
    if today.month >= 4:
        return f"{today.year}-{str(today.year + 1)[-2:]}"
    return f"{today.year - 1}-{str(today.year)[-2:]}"


def build_url(today: date) -> str:
    """Build InvestorGain's dynamic report API URL."""

    month = today.month
    year = today.year
    financial_year = get_financial_year(today)

    return (
        f"{BASE_URL}/1/{month}/{year}/{financial_year}/0/all"
        f"?search=&v=23-18"
    )


def clean_html(value: str) -> str:
    """Remove HTML tags/entities from InvestorGain fields."""
    if not value:
        return ""

    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    return value.strip()


def extract_gmp(value: str) -> int | None:
    """
    Extract GMP from InvestorGain's HTML field.

    Examples:
        ₹38 <b>...</b>  -> 38
        ₹--            -> None
    """
    if not value:
        return None

    value = html.unescape(value)

    # Remove HTML first
    text = re.sub(r"<[^>]+>", " ", value)

    # Look for rupee amount
    match = re.search(r"₹\s*([\d,]+)", text)

    if not match:
        return None

    return int(match.group(1).replace(",", ""))


def extract_lot(value: str) -> int | None:
    """Extract numeric retail lot size."""
    if not value:
        return None

    match = re.search(r"\d[\d,]*", str(value))

    if not match:
        return None

    return int(match.group(0).replace(",", ""))


def fetch_data(today: date) -> list[dict]:
    """Fetch IPO data from InvestorGain."""

    url = build_url(today)

    print("Fetching:")
    print(url)
    print()

    session = requests.Session()

    # Don't use HTTP_PROXY / HTTPS_PROXY environment variables
    session.trust_env = False

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.investorgain.com/",
        "Origin": "https://www.investorgain.com",
    }

    response = session.get(
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if "reportTableData" not in data:
        raise RuntimeError(
            "InvestorGain response does not contain reportTableData"
        )

    return data["reportTableData"]


def build_table(rows: list[dict], today: date) -> pd.DataFrame:
    """Filter Mainboard IPOs and build the final table."""

    result = []

    for row in rows:

        # ---------------------------------------------------------
        # 1. Mainboard only
        # ---------------------------------------------------------
        category = str(row.get("~ipo_category1", "")).strip().upper()

        if category != "IPO":
            continue

        # ---------------------------------------------------------
        # 2. Use actual sortable dates
        # ---------------------------------------------------------
        open_date = row.get("~Srt_Open", "")
        close_date = row.get("~Srt_Close", "")

        if not open_date or not close_date:
            continue

        try:
            open_dt = date.fromisoformat(open_date)
            close_dt = date.fromisoformat(close_date)
        except ValueError:
            continue

        # ---------------------------------------------------------
        # 3. Only IPOs that are OPEN today
        #    This includes "Closing Today"
        # ---------------------------------------------------------
        if not (open_dt <= today <= close_dt):
            continue

        # ---------------------------------------------------------
        # 4. Extract fields
        # ---------------------------------------------------------
        name = row.get("~ipo_name", "").strip()

        gmp = extract_gmp(row.get("GMP", ""))

        lot = extract_lot(row.get("Lot", ""))

        # GMP × lot
        estimated_profit = (
            gmp * lot
            if gmp is not None and lot is not None
            else None
        )

        # InvestorGain's actual ranking/order
        rank = row.get("~orderby1", 999999)

        result.append(
            {
                "rank": int(rank),
                "Ipo name": name,
                "Start date": open_dt.strftime("%d-%b"),
                "last date": close_dt.strftime("%d-%b"),
                "current gmp": gmp,
                "retail lot size": lot,
                "Est. profit/lot": estimated_profit,
            }
        )

    df = pd.DataFrame(result)

    if df.empty:
        return df

    # -------------------------------------------------------------
    # Sort by estimated profit DESCENDING
    # -------------------------------------------------------------
    df = df.sort_values(
        by="Est. profit/lot",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)

    # Convert internal order into our display rank
    df["rank"] = range(1, len(df) + 1)

    return df


def format_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Format values for console display."""

    display_df = df.copy()

    display_df["rank"] = display_df["rank"].astype(str)

    display_df["current gmp"] = display_df["current gmp"].apply(
        lambda x: "₹--" if pd.isna(x) else f"₹{int(x):,}"
    )

    display_df["retail lot size"] = display_df["retail lot size"].apply(
        lambda x: "--" if pd.isna(x) else f"{int(x):,}"
    )

    display_df["Est. profit/lot"] = display_df["Est. profit/lot"].apply(
        lambda x: "₹--" if pd.isna(x) else f"₹{int(x):,}"
    )

    display_df.columns = [
        "Rank",
        "IPO Name",
        "Start Date",
        "Last Date",
        "Current GMP",
        "Retail Lot",
        "Est. Profit/Lot",
    ]

    return display_df


# =====================================================================
# Visual constants
# =====================================================================

COLOR_BG = "#0B1220"          # page background (deep navy, premium feel)
COLOR_CARD = "#FFFFFF"
COLOR_HEADER_GRAD_1 = "#4F46E5"   # indigo
COLOR_HEADER_GRAD_2 = "#7C3AED"   # violet
COLOR_ROW_EVEN = "#F8FAFC"
COLOR_ROW_ODD = "#FFFFFF"
COLOR_TEXT_DARK = "#0F172A"
COLOR_TEXT_MUTED = "#64748B"
COLOR_GRID = "#E2E8F0"

STATUS_STYLE = {
    "open": {
        "face": "#DCFCE7",
        "edge": "#16A34A",
        "text": "#15803D",
        "label": "OPEN",
        "dot": "#22C55E",
    },
    "closing_today": {
        "face": "#FFEDD5",
        "edge": "#EA580C",
        "text": "#C2410C",
        "label": "CLOSING TODAY",
        "dot": "#F97316",
    },
    "closed": {
        "face": "#FEE2E2",
        "edge": "#DC2626",
        "text": "#B91C1C",
        "label": "CLOSED",
        "dot": "#EF4444",
    },
}


def get_status_key(row, today: date) -> str:
    start = pd.to_datetime(row["Start date"], format="%d-%b")
    end = pd.to_datetime(row["last date"], format="%d-%b")

    start_date = date(today.year, start.month, start.day)
    end_date = date(today.year, end.month, end.day)

    if end_date < start_date:
        end_date = date(today.year + 1, end.month, end.day)

    if today == end_date:
        return "closing_today"
    elif today < end_date:
        return "open"
    else:
        return "closed"


def profit_tier_color(value) -> tuple[str, str]:
    """Return (face_color, text_color) for the profit cell based on tier."""
    if pd.isna(value):
        return "#F1F5F9", "#94A3B8"
    v = int(value)
    if v >= 5000:
        return "#DCFCE7", "#15803D"    # strong green
    if v >= 2000:
        return "#ECFDF5", "#16A34A"    # light green
    if v > 0:
        return "#FEFCE8", "#A16207"    # amber, modest profit
    return "#FEE2E2", "#B91C1C"        # loss / zero, red tint


def draw_status_badge(ax, x_center, y_center, width, height, style):
    """Draw a rounded pill badge with a colored dot + label (no emoji)."""

    pill = mpatches.FancyBboxPatch(
        (x_center - width / 2, y_center - height / 2),
        width,
        height,
        boxstyle=f"round,pad=0,rounding_size={height / 2}",
        linewidth=1.1,
        edgecolor=style["edge"],
        facecolor=style["face"],
        transform=ax.transData,
        zorder=5,
    )
    ax.add_patch(pill)

    dot_radius = height * 0.22
    dot_x = x_center - width / 2 + dot_radius * 1.6
    dot = mpatches.Circle(
        (dot_x, y_center),
        radius=dot_radius,
        facecolor=style["dot"],
        edgecolor="none",
        zorder=6,
    )
    ax.add_patch(dot)

    ax.text(
        dot_x + dot_radius * 1.9,
        y_center,
        style["label"],
        fontsize=7.3,
        fontweight="bold",
        color=style["text"],
        ha="left",
        va="center",
        zorder=6,
    )


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{int(round(c*255)):02X}" for c in rgb)


def _make_gradient(c1: str, c2: str, n: int):
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    out = []
    for i in range(n):
        t = i / max(n - 1, 1)
        out.append(_rgb_to_hex((
            r1 + (r2 - r1) * t,
            g1 + (g2 - g1) * t,
            b1 + (b2 - b1) * t,
        )))
    return out


def save_table_image(
    df: pd.DataFrame,
    today: date,
    output_path: Path,
) -> None:
    """Generate a colorful, modern IPO tracker PNG (no emoji glyphs)."""

    if df.empty:
        print("No Mainboard IPOs are currently open.")
        return

    display_df = df.copy()
    display_df["status_key"] = display_df.apply(
        lambda r: get_status_key(r, today), axis=1
    )

    n_rows = len(display_df)

    columns = [
        ("", 0.000, 0.045),          # colored left accent strip
        ("RANK", 0.045, 0.115),
        ("IPO NAME", 0.115, 0.360),
        ("STATUS", 0.360, 0.520),
        ("OPEN", 0.520, 0.610),
        ("CLOSE", 0.610, 0.700),
        ("GMP", 0.700, 0.815),
        ("LOT SIZE", 0.815, 0.900),
        ("EST. PROFIT/LOT", 0.900, 1.000),
    ]

    row_h = 0.72          # inches per row (approx, before scaling)
    header_h_in = 1.55
    footer_h_in = 0.55
    fig_w = 16.5
    fig_h = header_h_in + n_rows * row_h + footer_h_in

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=190)
    fig.patch.set_facecolor(COLOR_BG)

    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    margin_x = 0.018

    header_frac = header_h_in / fig_h
    footer_frac = footer_h_in / fig_h
    table_frac = 1 - header_frac - footer_frac

    card_left = margin_x
    card_right = 1 - margin_x
    card_top = 1 - 0.012
    card_bottom = 0.012

    # Card background (rounded, white)
    card = mpatches.FancyBboxPatch(
        (card_left, card_bottom),
        card_right - card_left,
        card_top - card_bottom,
        boxstyle="round,pad=0,rounding_size=0.012",
        linewidth=0,
        facecolor=COLOR_CARD,
        zorder=0,
    )
    ax.add_patch(card)

    # Header gradient banner
    header_bottom = card_top - header_frac
    n_grad = 120
    grad_colors = _make_gradient(COLOR_HEADER_GRAD_1, COLOR_HEADER_GRAD_2, n_grad)
    strip_w = (card_right - card_left) / n_grad
    for i, c in enumerate(grad_colors):
        rect = mpatches.Rectangle(
            (card_left + i * strip_w, header_bottom),
            strip_w * 1.02,
            card_top - header_bottom,
            linewidth=0,
            facecolor=c,
            zorder=1,
        )
        ax.add_patch(rect)

    # Header text
    text_left = card_left + 0.018
    ax.text(
        text_left,
        card_top - header_frac * 0.28,
        "MAINBOARD IPO TRACKER",
        fontsize=12.5,
        fontweight="bold",
        color="#E0E7FF",
        va="top",
        ha="left",
        zorder=2,
    )
    ax.text(
        text_left,
        card_top - header_frac * 0.62,
        "IPO GMP & Retail Profit",
        fontsize=27,
        fontweight="bold",
        color="#FFFFFF",
        va="top",
        ha="left",
        zorder=2,
    )

    text_right = card_right - 0.018
    ax.text(
        text_right,
        card_top - header_frac * 0.32,
        today.strftime("%d %b %Y"),
        fontsize=13,
        fontweight="bold",
        color="#FFFFFF",
        ha="right",
        va="top",
        zorder=2,
    )
    # LIVE badge
    live_w, live_h = 0.10, header_frac * 0.22
    live_cx = text_right - live_w / 2
    live_cy = card_top - header_frac * 0.62
    live_pill = mpatches.FancyBboxPatch(
        (live_cx - live_w / 2, live_cy - live_h / 2),
        live_w,
        live_h,
        boxstyle=f"round,pad=0,rounding_size={live_h/2}",
        linewidth=0,
        facecolor="#22C55E",
        zorder=2,
    )
    ax.add_patch(live_pill)
    ax.text(
        live_cx,
        live_cy,
        "\u25CF LIVE DATA",
        fontsize=8,
        fontweight="bold",
        color="#FFFFFF",
        ha="center",
        va="center",
        zorder=3,
    )

    # Table header row
    col_header_h = table_frac * 0.09
    col_header_top = header_bottom
    col_header_bottom = col_header_top - col_header_h

    header_row_bg = mpatches.Rectangle(
        (card_left, col_header_bottom),
        card_right - card_left,
        col_header_h,
        linewidth=0,
        facecolor="#EEF2FF",
        zorder=1,
    )
    ax.add_patch(header_row_bg)

    def col_x(frac):
        return card_left + frac * (card_right - card_left)

    for label, f0, f1 in columns:
        if not label:
            continue
        cx = col_x((f0 + f1) / 2)
        ha = "left" if label == "IPO NAME" else "center"
        tx = col_x(f0) + 0.006 if ha == "left" else cx
        ax.text(
            tx,
            (col_header_top + col_header_bottom) / 2,
            label,
            fontsize=9,
            fontweight="bold",
            color="#4338CA",
            ha=ha,
            va="center",
            zorder=2,
        )

    # Data rows
    rows_top = col_header_bottom
    rows_bottom = card_bottom + footer_frac * 0.15
    row_height = (rows_top - rows_bottom) / n_rows

    RANK_MEDAL = {1: "#F59E0B", 2: "#94A3B8", 3: "#B45309"}  # gold/silver/bronze

    for i in range(n_rows):
        r = display_df.iloc[i]
        y_top = rows_top - i * row_height
        y_bottom = y_top - row_height
        y_center = (y_top + y_bottom) / 2

        row_bg = COLOR_ROW_EVEN if i % 2 == 0 else COLOR_ROW_ODD
        bg_rect = mpatches.Rectangle(
            (card_left, y_bottom),
            card_right - card_left,
            row_height,
            linewidth=0,
            facecolor=row_bg,
            zorder=1,
        )
        ax.add_patch(bg_rect)

        ax.plot(
            [card_left, card_right],
            [y_bottom, y_bottom],
            color=COLOR_GRID,
            linewidth=0.6,
            zorder=2,
        )

        rank = int(r["rank"])

        # Left accent strip
        accent_color = RANK_MEDAL.get(rank, "#C7D2FE")
        accent_rect = mpatches.Rectangle(
            (card_left, y_bottom),
            columns[0][2] * (card_right - card_left) + 0.001,
            row_height,
            linewidth=0,
            facecolor=accent_color,
            zorder=2,
        )
        ax.add_patch(accent_rect)

        # Rank number (medal circle for top 3)
        rank_cx = col_x((columns[1][1] + columns[1][2]) / 2)
        if rank <= 3:
            medal = mpatches.Circle(
                (rank_cx, y_center),
                radius=row_height * 0.32,
                facecolor=accent_color,
                edgecolor="none",
                zorder=3,
            )
            ax.add_patch(medal)
            ax.text(
                rank_cx, y_center, str(rank),
                fontsize=10, fontweight="bold", color="#FFFFFF",
                ha="center", va="center", zorder=4,
            )
        else:
            ax.text(
                rank_cx, y_center, str(rank),
                fontsize=10, fontweight="bold", color=COLOR_TEXT_MUTED,
                ha="center", va="center", zorder=4,
            )

        # IPO name
        name_x = col_x(columns[2][1]) + 0.006
        ax.text(
            name_x, y_center, str(r["Ipo name"]),
            fontsize=10.5, fontweight="bold", color=COLOR_TEXT_DARK,
            ha="left", va="center", zorder=4,
        )

        # Status badge
        style = STATUS_STYLE[r["status_key"]]
        status_cx = col_x((columns[3][1] + columns[3][2]) / 2)
        draw_status_badge(
            ax, status_cx, y_center,
            width=columns[3][2] - columns[3][1] - 0.012,
            height=row_height * 0.42,
            style=style,
        )

        # Start / close dates
        start_cx = col_x((columns[4][1] + columns[4][2]) / 2)
        ax.text(start_cx, y_center, r["Start date"], fontsize=9.8,
                 color="#475569", ha="center", va="center", zorder=4)
        close_cx = col_x((columns[5][1] + columns[5][2]) / 2)
        ax.text(close_cx, y_center, r["last date"], fontsize=9.8,
                 color="#475569", ha="center", va="center", zorder=4)

        # GMP
        gmp_val = r["current gmp"]
        gmp_text = "₹--" if pd.isna(gmp_val) else f"₹{int(gmp_val):,}"
        gmp_color = "#94A3B8" if pd.isna(gmp_val) else "#2563EB"
        gmp_cx = col_x((columns[6][1] + columns[6][2]) / 2)
        ax.text(gmp_cx, y_center, gmp_text, fontsize=10.5, fontweight="bold",
                 color=gmp_color, ha="center", va="center", zorder=4)

        # Lot size
        lot_val = r["retail lot size"]
        lot_text = "--" if pd.isna(lot_val) else f"{int(lot_val):,}"
        lot_cx = col_x((columns[7][1] + columns[7][2]) / 2)
        ax.text(lot_cx, y_center, lot_text, fontsize=9.8,
                 color="#475569", ha="center", va="center", zorder=4)

        # Est profit/lot -> colored chip by tier
        profit_val = r["Est. profit/lot"]
        face, txt_color = profit_tier_color(profit_val)
        profit_text = "₹--" if pd.isna(profit_val) else f"₹{int(profit_val):,}"
        _, chip_f0, chip_f1 = columns[8]
        chip_w = (chip_f1 - chip_f0) * (card_right - card_left) - 0.018
        chip_h = row_height * 0.5
        chip_cx = col_x((chip_f0 + chip_f1) / 2)
        chip = mpatches.FancyBboxPatch(
            (chip_cx - chip_w / 2, y_center - chip_h / 2),
            chip_w, chip_h,
            boxstyle=f"round,pad=0,rounding_size={chip_h/2}",
            linewidth=0,
            facecolor=face,
            zorder=3,
        )
        ax.add_patch(chip)
        ax.text(chip_cx, y_center, profit_text, fontsize=10.3, fontweight="bold",
                 color=txt_color, ha="center", va="center", zorder=4)

    # Footer legend
    footer_y = card_bottom + footer_frac * 0.5
    lx = card_left + 0.016
    for key in ["open", "closing_today", "closed"]:
        style = STATUS_STYLE[key]
        dot = mpatches.Circle((lx, footer_y), radius=0.0068,
                                facecolor=style["dot"], edgecolor="none", zorder=3)
        ax.add_patch(dot)
        label = style["label"].title()
        ax.text(lx + 0.013, footer_y, label, fontsize=8.3,
                 color="#475569", ha="left", va="center", zorder=3)
        lx += 0.028 + 0.0068 * len(label)

    ax.text(
        card_right - 0.014, footer_y, "Source: InvestorGain",
        fontsize=8, color="#94A3B8", ha="right", va="center", zorder=3,
    )

    fig.savefig(
        output_path,
        dpi=190,
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)


def main() -> None:
    today = date.today()

    rows = fetch_data(today)

    df = build_table(rows, today)

    if df.empty:
        print("No Mainboard IPOs open today.")
        return

    # Console table
    display_df = format_dataframe(df)

    print(display_df.to_string(index=False))
    print()

    # Save CSV as well
    csv_path = OUTPUT_DIR / f"ipo_gmp_{today.isoformat()}.csv"
    df.to_csv(csv_path, index=False)

    # Save image (fixed filename for a stable link, plus a dated copy)
    latest_path = OUTPUT_DIR / "latest.png"
    dated_path = OUTPUT_DIR / f"ipo_gmp_{today.isoformat()}.png"

    save_table_image(df, today, latest_path)

    # keep a dated copy too, for history
    import shutil
    if latest_path.exists():
        shutil.copyfile(latest_path, dated_path)

    print(f"CSV   : {csv_path}")
    print(f"Image : {latest_path}  (also saved as {dated_path})")


if __name__ == "__main__":
    main()
