import json
from datetime import date

from groq import Groq

from config import GROQ_API_KEY, now_wib

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def parse_expense_with_ai(text: str) -> list[dict]:
    if client is None:
        raise RuntimeError("GROQ_API_KEY belum dikonfigurasi.")

    today = now_wib().date()
    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": (
                    "Anda mengekstrak pengeluaran uang dari teks pengguna. "
                    f"Tanggal hari ini {today.isoformat()}. Kembalikan hanya objek JSON "
                    'dengan format {"expenses":[{"nominal":20000,'
                    '"keterangan":"Makan Warteg","tanggal":"YYYY-MM-DD"}]}. '
                    "Nominal harus integer rupiah positif, termasuk konversi rb/ribu/k "
                    "dan jt/juta. Tanggal harus YYYY-MM-DD; tafsirkan kemarin relatif "
                    "terhadap tanggal hari ini, dan gunakan hari ini jika tidak disebut. "
                    "Pisahkan setiap pengeluaran menjadi objek tersendiri. Jika tidak "
                    'ada pengeluaran valid, kembalikan {"expenses":[]}.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(text, ensure_ascii=False),
            },
        ],
        model="openai/gpt-oss-20b",
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("Groq mengembalikan respons kosong.")
    result = json.loads(content)
    expenses = result.get("expenses")
    if not isinstance(expenses, list):
        raise ValueError("Respons AI tidak memiliki daftar expenses yang valid.")
    if len(expenses) > 20:
        raise ValueError("AI mengembalikan terlalu banyak transaksi.")

    validated = []
    for expense in expenses:
        if not isinstance(expense, dict):
            raise ValueError("Data pengeluaran AI tidak valid.")
        nominal = expense.get("nominal")
        keterangan = expense.get("keterangan")
        tanggal = expense.get("tanggal")
        if (
            not isinstance(nominal, int)
            or isinstance(nominal, bool)
            or not 0 < nominal <= 1_000_000_000
            or not isinstance(keterangan, str)
            or not keterangan.strip()
            or len(keterangan.strip()) > 200
            or not isinstance(tanggal, str)
        ):
            raise ValueError("Data pengeluaran AI tidak lolos validasi.")
        try:
            date.fromisoformat(tanggal)
        except ValueError as exc:
            raise ValueError("Tanggal pengeluaran dari AI tidak valid.") from exc
        if date.fromisoformat(tanggal).isoformat() != tanggal:
            raise ValueError("Tanggal pengeluaran harus berformat YYYY-MM-DD.")
        validated.append({
            "nominal": nominal,
            "keterangan": keterangan.strip(),
            "tanggal": tanggal,
        })

    return validated
