import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
import os
import yfinance as yf
import pandas as pd
import pytz
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# --------- ΡΥΘΜΙΣΕΙΣ ---------
TIMEZONE = "Europe/Athens"
TICKER_MAP = {
    "GD.AT": "Γενικός Δείκτης",      # Athens General Index (Yahoo Finance)
    "HELPE.AT": "Ελληνικά Πετρέλαια" # Hellenic Petroleum (Yahoo Finance)
}
GREEK_DAYS = {
    0: "Δευτέρα",
    1: "Τρίτη",
    2: "Τετάρτη",
    3: "Πέμπτη",
    4: "Παρασκευή",
}
# Διαβάζουμε από ENV vars (για ασφάλεια στο Render)
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")
# ------------------------------

def greek_day_name(dt):
    return GREEK_DAYS.get(dt.weekday(), "")

def weekly_report_with_plot(ticker_symbol):
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    # Περασμένη εβδομάδα (Δευτέρα–Παρασκευή)
    last_monday = now - timedelta(days=now.weekday() + 7)
    last_saturday = last_monday + timedelta(days=6)
    start = last_monday.date()
    end = (last_saturday + timedelta(days=1)).date()

    # Κατέβασμα δεδομένων από yfinance
    df = yf.download(ticker_symbol, start=start, end=end, interval="1d", progress=False)
    if df.empty:
        print(f"⚠️ Δεν βρέθηκαν δεδομένα για {TICKER_MAP.get(ticker_symbol, ticker_symbol)}")
        return None

    rows = []
    for date, row in df.iterrows():
        rows.append({
            "Ημερομηνία": date.date(),
            "Ημέρα": greek_day_name(date),
            "Close": float(row["Close"])
        })

    part = pd.DataFrame(rows).sort_values("Ημερομηνία")
    day_order = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή"]
    present_days = [d for d in day_order if d in part["Ημέρα"].unique()]
    close_row = part.set_index("Ημέρα")["Close"].reindex(present_days)

    # Φτιάχνουμε report table
    report = pd.DataFrame(
        [close_row.values],
        index=["Τιμή Κλεισίματος"],
        columns=present_days
    )
    report_fmt = report.applymap(lambda x: f"{x:.2f}" if pd.notna(x) else "")
    last_close = part["Close"].iloc[-1]

    # Δημιουργία figure
    fig, (ax_table, ax_plot) = plt.subplots(
        nrows=2, figsize=(10, 6), gridspec_kw={"height_ratios": [1, 2]}
    )

    # Πίνακας
    ax_table.axis("off")
    table = ax_table.table(
        cellText=report_fmt.values,
        colLabels=report_fmt.columns,
        rowLabels=report_fmt.index,
        cellLoc="center",
        loc="center"
    )
    table.scale(1.2, 1.8)
    for _, cell in table.get_celld().items():
        cell.set_fontsize(12)
        cell.set_text_props(weight='bold')

    ax_table.set_title(
        f"Εβδομαδιαίο Report — {TICKER_MAP[ticker_symbol]} ({last_close:.2f}€)",
        fontsize=16, fontweight='bold', pad=10
    )

    # Διάγραμμα
    labels = [f"{d} ({day})" for d, day in zip(part["Ημερομηνία"].astype(str), part["Ημέρα"])]
    ax_plot.plot(labels, part["Close"], marker="o")
    ax_plot.set_title(f"{TICKER_MAP[ticker_symbol]} — Τιμή Κλεισίματος (Εβδομάδα)",
                      fontsize=14, fontweight='bold')
    ax_plot.set_xlabel("Ημερομηνία (Ημέρα)")
    ax_plot.set_ylabel("Τιμή Κλεισίματος (€)")
    ax_plot.grid(True)
    ax_plot.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax_plot.yaxis.set_major_locator(mticker.MaxNLocator(nbins=8))
    plt.setp(ax_plot.get_xticklabels(), rotation=45, ha="right")

    plt.tight_layout()

    # Αποθήκευση εικόνας
    os.makedirs("weekly_reports", exist_ok=True)
    filename = f"weekly_reports/{TICKER_MAP[ticker_symbol].replace(' ', '_')}_report.jpg"
    plt.savefig(filename, dpi=300, bbox_inches="tight", format="jpeg")
    plt.close(fig)

    return filename

def send_email_with_reports(files):
    now = datetime.now()
    subject = "📊 Εβδομαδιαία Reports"
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject

    for file_path in files:
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                img_data = f.read()
            part = MIMEImage(img_data, _subtype="jpeg")
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file_path)}")
            msg.attach(part)
        else:
            print(f"⚠️ Δεν βρέθηκε το αρχείο: {file_path}")

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
    server.sendmail(EMAIL_SENDER, RECEIVER_EMAIL, msg.as_string())
    server.quit()

    print(f"📩 Email στάλθηκε στο {RECEIVER_EMAIL} στις {now.strftime('%H:%M:%S')}")

def main():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if now.weekday() == 5:  # Σάββατο
        print("📌 Δημιουργία εβδομαδιαίων reports...")
        file1 = weekly_report_with_plot("GD.AT")
        file2 = weekly_report_with_plot("HELPE.AT")
        files = [f for f in [file1, file2] if f]
        if files:
            send_email_with_reports(files)
    else:
        print("⏭ Σήμερα δεν είναι Σάββατο — δεν στέλνω report.")

if __name__ == "__main__":
    main()
