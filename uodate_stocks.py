import pandas as pd
import yfinance as yf
import json
from datetime import datetime, timezone, timedelta

# -------------------------
# 1. 銘柄リストを読み込む
# -------------------------
stocks = pd.read_csv("stocks.csv")

# TRUEの銘柄だけ使う
stocks = stocks[stocks["enabled"] == True]

# 日本株コードを Yahoo Finance 用に変換
tickers = [f"{code}.T" for code in stocks["code"]]

print("取得する銘柄:", tickers)


# -------------------------
# 2. 株価をまとめて取得
# -------------------------
data = yf.download(
    tickers,
    period="5d",
    interval="1d",
    group_by="ticker",
    threads=True
)

results = []

# -------------------------
# 3. 各銘柄の騰落率を計算
# -------------------------
for _, stock in stocks.iterrows():

    code = str(stock["code"])
    ticker = f"{code}.T"

    try:
        prices = data[ticker]["Close"].dropna()

        if len(prices) < 2:
            print(f"{ticker}: データ不足")
            continue

        previous_close = float(prices.iloc[-2])
        current_price = float(prices.iloc[-1])

        change_percent = (
            (current_price - previous_close)
            / previous_close
            * 100
        )

        results.append({
            "code": code,
            "name": stock["name"],
            "industry": stock["industry"],
            "price": round(current_price, 2),
            "change_percent": round(change_percent, 2)
        })

    except Exception as e:
        print(f"{ticker}: エラー {e}")


# -------------------------
# 4. 業界平均を計算
# -------------------------
results_df = pd.DataFrame(results)

industries = []

if not results_df.empty:

    industry_avg = (
        results_df
        .groupby("industry")["change_percent"]
        .mean()
        .sort_values(ascending=False)
    )

    for industry, avg in industry_avg.items():
        industries.append({
            "industry": industry,
            "change_percent": round(float(avg), 2)
        })


# -------------------------
# 5. 急変銘柄を取得
# -------------------------
top_gainers = (
    results_df
    .sort_values("change_percent", ascending=False)
    .head(10)
    .to_dict("records")
)

top_losers = (
    results_df
    .sort_values("change_percent", ascending=True)
    .head(10)
    .to_dict("records")
)


# -------------------------
# 6. JSONとして保存
# -------------------------
jst = timezone(timedelta(hours=9))

output = {
    "updated_at": datetime.now(jst).strftime("%Y-%m-%d %H:%M"),
    "industries": industries,
    "top_gainers": top_gainers,
    "top_losers": top_losers
}

with open(
    "data.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        output,
        f,
        ensure_ascii=False,
        indent=2
    )

print("data.json を作成しました")
