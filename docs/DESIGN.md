# DESIGN.md - Deep Harbor Theme Specifications

This document outlines the visual and structural design for Dredge, following a professional, industrial, and nautical "Submarine Control Room" aesthetic.

## 1. The 'Deep Harbor' Theme

**Philosophy:** Dark, precise, data-dense. Avoid bright/playful colors. Use high contrast for critical data.

### Color Palette (CSS Variables)

| Variable | Hex Code | Description | Usage |
| :--- | :--- | :--- | :--- |
| `--bg-base` | `#0D1B2A` | Deep Navy | Main Background |
| `--bg-surface` | `#1B263B` | Steel Blue | Card/Sidebar Background |
| `--primary` | `#0077B6` | Cerulean | Main Buttons, Links, Highlights |
| `--primary-hover` | `#0096C7` | Lighter Blue | Hover States |
| `--accent` | `#48CAE4` | Cyan/Aqua | Highlights, Active States |
| `--danger` | `#D97D54` | Rusted Orange | Waste metrics, Delete actions (NO bright red) |
| `--text-main` | `#E0E1DD` | Off-White | Primary Text |
| `--text-muted` | `#778DA9` | Blue-Gray | Secondary Text |

## 2. Layout Structure (templates/base.html)

Implement a **Fixed Sidebar Layout** using CSS Grid or Flexbox.

### Sidebar (~250px Fixed Width)
- **Top:** "Abyssal Vortex" Logo (blue/cyan abstract swirl) + "Dredge" text.
- **Nav:** Vertical links for:
  - Dashboard
  - Images
  - Volumes
  - Policies
  - Logs
- **Bottom:**
  - Scope Dropdown (Local Socket vs Remote Registry).
  - Small "Server Status" indicator (Green/Red dot).

### Main Content
- Scrollable area.
- Max-width container for readability on large screens.

## 3. Dashboard View (templates/dashboard.html)

### KPI Cards (Top Row)
1.  **Monthly Waste ($)**: Value in Rusted Orange (`--danger`).
2.  **Reclaimable Space (GB)**: Value in Cyan (`--accent`).
3.  **Efficiency Score (%)**: Value in White (`--text-main`).

### Action Bar
- **Scan Now Button**: Primary style (`--primary`), triggers `hx-post="/scan"`.
- **Dry Run Toggle**: Switch control.

## 4. Image Table (templates/images.html)

High-density data table.

### Columns
- Checkbox (for bulk actions)
- Repository
- Tag
- Size
- Created (Relative time, e.g., "2 days ago")
- Status Badge

### Badging Strategy
| Status | Color | Visual Style |
| :--- | :--- | :--- |
| **Safe** | Cyan/Green | Solid background or Outline |
| **Dangling** | Rusted Orange (`--danger`) | Solid background |
| **Quarantined** | Striped/Grey | Muted, indicates inactive/pending delete |
