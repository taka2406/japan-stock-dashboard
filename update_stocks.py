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

# 銘柄ごとのグラフ用データ
price_history = {}

# 業界平均を作るための
# 日付ごとのデータ
industry_history_records = []


# -------------------------
# 3. 各銘柄の1か月騰落率
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
                - first_price
            )
            / first_price
            * 100
        )


        # -------------------------
        # ランキング用
        # -------------------------

        results.append({

            "code":
                code,

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
        # 銘柄グラフ用
        #
        # 1か月前 = 100
        # -------------------------

        history = []


        for date, price in prices.items():

            normalized = (
                float(price)
                / first_price
                * 100
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


            # -------------------------
            # 業界平均用データ
            # -------------------------

            industry_history_records.append({

                "date":
                    date.strftime(
                        "%m/%d"
                    ),

                "industry":
                    stock["industry"],

                "value":
                    normalized

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
# 5. 業界ランキング
#
# 各業界の
# 構成銘柄の1か月騰落率平均
# -------------------------

industries = []

top_industry_names = []


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


    # 全業界ランキング
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
    # 上位10業界
    # -------------------------

    top_industry_names = (

        industry_avg

        .head(10)

        .index

        .tolist()

    )


# -------------------------
# 6. 業界平均の
# 日ごとの推移を計算
# -------------------------

industry_history_df = pd.DataFrame(
    industry_history_records
)


top_industries = []


if not industry_history_df.empty:


    # 日付ごと・業界ごとに
    # 平均を計算
    industry_daily_avg = (

        industry_history_df

        .groupby(
            [
                "industry",
                "date"
            ]
        )[
            "value"
        ]

        .mean()

        .reset_index()

    )


    # 上位10業界だけ
    for industry in top_industry_names:


        history_df = (

            industry_daily_avg

            [
                industry_daily_avg[
                    "industry"
                ]
                == industry
            ]

            .copy()

        )


        history = []


        for _, row in (

            history_df

            .iterrows()

        ):

            history.append({

                "date":
                    row["date"],

                "value":
                    round(
                        float(
                            row["value"]
                        ),
                        2
                    )

            })


        # 業界の最終騰落率を取得

        industry_change = (

            next(

                (
                    item[
                        "change_percent"
                    ]

                    for item in industries

                    if item[
                        "industry"
                    ]
                    == industry

                ),

                0

            )

        )


        top_industries.append({

            "industry":
                industry,

            "change_percent":
                industry_change,

            "history":
                history

        })


# -------------------------
# 7. 1か月値上がり
# TOP10銘柄
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
# 8. JSONを保存
# -------------------------

jst = timezone(
    timedelta(hours=9)
)


output = {

    "updated_at":

        datetime.now(jst).strftime(
            "%Y-%m-%d %H:%M"
        ),


    # 全業界ランキング
    "industries":
        industries,


    # 上位10業界の
    # 折れ線グラフ用データ
    "top_industries":
        top_industries,


    # 値上がりTOP10銘柄
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
