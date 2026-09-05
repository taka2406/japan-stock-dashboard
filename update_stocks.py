import pandas as pd
import yfinance as yf
import json
from datetime import datetime, timezone, timedelta


# =========================
# 1. 銘柄リスト
# =========================

stocks = pd.read_csv("stocks.csv")

stocks = stocks[
    stocks["enabled"] == True
].copy()

stocks["code"] = (
    stocks["code"]
    .astype(str)
    .str.zfill(4)
)

# テーマ列が存在しない場合に備える
for col in ["theme1", "theme2", "theme3"]:

    if col not in stocks.columns:
        stocks[col] = ""


tickers = [
    f"{code}.T"
    for code in stocks["code"]
]

print("取得する銘柄数:", len(tickers))


# =========================
# 2. 株価取得
# =========================

data = yf.download(
    tickers,
    period="1mo",
    interval="1d",
    group_by="ticker",
    threads=True
)


results = []

price_history = {}

industry_history_records = []

theme_history_records = []


# =========================
# 3. 各銘柄
# =========================

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


        first_price = float(
            prices.iloc[0]
        )

        current_price = float(
            prices.iloc[-1]
        )


        change_percent = (
            (
                current_price
                - first_price
            )
            / first_price
            * 100
        )


        results.append({

            "code": code,

            "name": stock["name"],

            "industry": stock["industry"],

            "price": round(
                current_price,
                2
            ),

            "month_change_percent":
                round(
                    change_percent,
                    2
                )

        })


        # =========================
        # 銘柄の1か月推移
        # =========================

        history = []


        for date, price in prices.items():

            normalized = (
                float(price)
                / first_price
                * 100
            )

            date_text = date.strftime(
                "%m/%d"
            )


            history.append({

                "date": date_text,

                "value": round(
                    normalized,
                    2
                )

            })


            # 業界平均

            industry_history_records.append({

                "date": date_text,

                "industry":
                    stock["industry"],

                "value": normalized

            })


            # =========================
            # テーマ
            # =========================

            themes = []


            for col in [
                "theme1",
                "theme2",
                "theme3"
            ]:

                value = stock[col]

                if pd.notna(value):

                    value = str(value).strip()

                    if value != "":

                        themes.append(value)


            # 同じテーマが
            # 複数欄に入っていても1回だけ

            themes = list(
                dict.fromkeys(themes)
            )


            for theme in themes:

                theme_history_records.append({

                    "date": date_text,

                    "theme": theme,

                    "value": normalized

                })


        price_history[code] = history


    except Exception as e:

        print(
            f"{ticker}: エラー {e}"
        )


# =========================
# 4. DataFrame
# =========================

results_df = pd.DataFrame(
    results
)


# =========================
# 5. 業界ランキング
# =========================

industries = []

top_industry_names = []


if not results_df.empty:

    industry_avg = (

        results_df

        .groupby("industry")
        ["month_change_percent"]

        .mean()

        .sort_values(
            ascending=False
        )

    )


    for industry, avg in (
        industry_avg.items()
    ):

        industries.append({

            "industry": industry,

            "change_percent":
                round(
                    float(avg),
                    2
                )

        })


    top_industry_names = (

        industry_avg

        .head(10)

        .index

        .tolist()

    )


# =========================
# 6. 業界グラフ
# =========================

industry_history_df = pd.DataFrame(
    industry_history_records
)

top_industries = []


if not industry_history_df.empty:

    daily = (

        industry_history_df

        .groupby(
            [
                "industry",
                "date"
            ]
        )["value"]

        .mean()

        .reset_index()

    )


    for industry in top_industry_names:

        temp = daily[
            daily["industry"]
            == industry
        ]

        history = []


        for _, row in temp.iterrows():

            history.append({

                "date": row["date"],

                "value": round(
                    float(row["value"]),
                    2
                )

            })


        change = next(

            (
                x["change_percent"]

                for x in industries

                if x["industry"]
                == industry
            ),

            0

        )


        top_industries.append({

            "industry": industry,

            "change_percent": change,

            "history": history

        })


# =========================
# 7. 業界別銘柄
# =========================

industry_stocks = {}


for _, item in results_df.iterrows():

    industry = item["industry"]

    code = item["code"]


    stock_data = {

        "code": code,

        "name": item["name"],

        "price": item["price"],

        "change_percent":
            item["month_change_percent"],

        "history":
            price_history.get(
                code,
                []
            )

    }


    if industry not in industry_stocks:

        industry_stocks[industry] = []


    industry_stocks[industry].append(
        stock_data
    )


for industry in industry_stocks:

    industry_stocks[industry].sort(

        key=lambda x:
            x["change_percent"],

        reverse=True

    )


# =========================
# 8. テーマランキング
# =========================

theme_stock_records = []


for _, stock in stocks.iterrows():

    code = stock["code"]

    result = results_df[
        results_df["code"]
        == code
    ]

    if result.empty:
        continue


    change = float(
        result.iloc[0]
        ["month_change_percent"]
    )


    themes = []


    for col in [
        "theme1",
        "theme2",
        "theme3"
    ]:

        value = stock[col]

        if pd.notna(value):

            value = str(value).strip()

            if value != "":
                themes.append(value)


    themes = list(
        dict.fromkeys(themes)
    )


    for theme in themes:

        theme_stock_records.append({

            "theme": theme,

            "code": code,

            "name": stock["name"],

            "price":
                float(
                    result.iloc[0]
                    ["price"]
                ),

            "change_percent": change,

            "history":
                price_history.get(
                    code,
                    []
                )

        })


theme_stock_df = pd.DataFrame(
    theme_stock_records
)


themes = []

top_theme_names = []


if not theme_stock_df.empty:

    theme_avg = (

        theme_stock_df

        .groupby("theme")
        ["change_percent"]

        .mean()

        .sort_values(
            ascending=False
        )

    )


    for theme, avg in (
        theme_avg.items()
    ):

        themes.append({

            "theme": theme,

            "change_percent":
                round(
                    float(avg),
                    2
                )

        })


    top_theme_names = (

        theme_avg

        .head(10)

        .index

        .tolist()

    )


# =========================
# 9. テーマの日次平均
# =========================

theme_history_df = pd.DataFrame(
    theme_history_records
)

top_themes = []


if not theme_history_df.empty:

    theme_daily = (

        theme_history_df

        .groupby(
            [
                "theme",
                "date"
            ]
        )["value"]

        .mean()

        .reset_index()

    )


    for theme in top_theme_names:

        temp = theme_daily[
            theme_daily["theme"]
            == theme
        ]

        history = []


        for _, row in temp.iterrows():

            history.append({

                "date": row["date"],

                "value": round(
                    float(row["value"]),
                    2
                )

            })


        change = next(

            (
                x["change_percent"]

                for x in themes

                if x["theme"]
                == theme
            ),

            0

        )


        top_themes.append({

            "theme": theme,

            "change_percent": change,

            "history": history

        })


# =========================
# 10. テーマ別銘柄
# =========================

theme_stocks = {}


if not theme_stock_df.empty:

    for theme in (
        theme_stock_df["theme"]
        .unique()
    ):

        temp = theme_stock_df[
            theme_stock_df["theme"]
            == theme
        ].copy()


        temp = temp.sort_values(

            "change_percent",

            ascending=False

        )


        theme_stocks[theme] = []


        for _, row in temp.iterrows():

            theme_stocks[theme].append({

                "code":
                    row["code"],

                "name":
                    row["name"],

                "price":
                    row["price"],

                "change_percent":
                    round(
                        float(
                            row["change_percent"]
                        ),
                        2
                    ),

                "history":
                    row["history"]

            })


# =========================
# 11. 株価TOP10
# =========================

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

        "code": code,

        "name": item["name"],

        "industry": item["industry"],

        "price": item["price"],

        "change_percent":
            item["month_change_percent"],

        "history":
            price_history.get(
                code,
                []
            )

    })


# =========================
# 12. JSON
# =========================

jst = timezone(
    timedelta(hours=9)
)


output = {

    "updated_at":
        datetime.now(jst).strftime(
            "%Y-%m-%d %H:%M"
        ),

    # 業界
    "industries":
        industries,

    "top_industries":
        top_industries,

    "industry_stocks":
        industry_stocks,

    # テーマ
    "themes":
        themes,

    "top_themes":
        top_themes,

    "theme_stocks":
        theme_stocks,

    # 銘柄
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
