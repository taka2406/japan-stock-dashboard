import pandas as pd
import yfinance as yf
import json
from datetime import datetime, timezone, timedelta

# -------------------------
# 1. 銘柄リストを読み込む
# -------------------------

stocks = pd.read_csv("stocks.csv")

stocks = stocks[
    stocks["enabled"] == True
]

# 証券コードを文字列にする
stocks["code"] = (
    stocks["code"]
    .astype(str)
    .str.zfill(4)
)

tickers = [
    f"{code}.T"
    for code in stocks["code"]
]

print("取得する銘柄数:", len(tickers))


# -------------------------
# 2. 約1か月分の株価を取得
# -------------------------

data = yf.download(
    tickers,
    period="1mo",
    interval="1d",
    group_by="ticker",
    threads=True
)


results = []

# グラフ用データ
price_history = {}


# -------------------------
# 3. 各銘柄の1か月騰落率を計算
# -------------------------

for _, stock in stocks.iterrows():

    code = stock["code"]

    ticker = f"{code}.T"

    try:

        prices = (
            data[ticker]["Close"]
            .dropna()
        )

        if len(prices) < 2:

            print(
                f"{ticker}: データ不足"
            )

            continue


        # -------------------------
        # 1か月前の価格
        # -------------------------

        first_price = float(
            prices.iloc[0]
        )


        # -------------------------
        # 最新価格
        # -------------------------

        current_price = float(
            prices.iloc[-1]
        )


        # -------------------------
        # 1か月騰落率
        # -------------------------

        change_percent = (
            (
                current_price
                -
                first_price
            )
            /
            first_price
            *
            100
        )


        # -------------------------
        # ランキング用
        # -------------------------

        results.append({

            "code": code,

            "name":
                stock["name"],

            "industry":
                stock["industry"],

            "price":
                round(
                    current_price,
                    2
                ),

            "month_change_percent":
                round(
                    change_percent,
                    2
                )

        })


        # -------------------------
        # グラフ用
        #
        # 1か月前 = 100
        # -------------------------

        history = []

        for date, price in prices.items():

            normalized = (
                float(price)
                /
                first_price
                *
                100
            )

            history.append({

                "date":
                    date.strftime(
                        "%m/%d"
                    ),

                "value":
                    round(
                        normalized,
                        2
                    )

            })


        price_history[code] = history


    except Exception as e:

        print(
            f"{ticker}: エラー {e}"
        )


# -------------------------
# 4. DataFrame
# -------------------------

results_df = pd.DataFrame(
    results
)


# -------------------------
# 5. 業界平均
#
# これは前日比ではなく
# 1か月騰落率に変更
# -------------------------

industries = []

if not results_df.empty:

    industry_avg = (

        results_df

        .groupby(
            "industry"
        )[
            "month_change_percent"
        ]

        .mean()

        .sort_values(
            ascending=False
        )

    )


    for industry, avg in (
        industry_avg.items()
    ):

        industries.append({

            "industry":
                industry,

            "change_percent":
                round(
                    float(avg),
                    2
                )

        })


# -------------------------
# 6. 1か月値上がり TOP10
# -------------------------

top_gainers_df = (

    results_df

    .sort_values(

        "month_change_percent",

        ascending=False

    )

    .head(10)

)


top_gainers = []

for _, item in (
    top_gainers_df.iterrows()
):

    code = item["code"]

    top_gainers.append({

        "code":
            code,

        "name":
            item["name"],

        "industry":
            item["industry"],

        "price":
            item["price"],

        "change_percent":
            item[
                "month_change_percent"
            ],

        "history":
            price_history.get(
                code,
                []
            )

    })


# -------------------------
# 7. JSONを保存
# -------------------------

jst = timezone(
    timedelta(hours=9)
)

output = {

    "updated_at":

        datetime.now(jst).strftime(
            "%Y-%m-%d %H:%M"
        ),


    "industries":
        industries,


    "top_gainers":
        top_gainers

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


print(
    "data.json を作成しました"
)
