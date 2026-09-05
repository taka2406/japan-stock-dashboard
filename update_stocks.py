```python
import pandas as pd
import yfinance as yf
import json
from datetime import datetime, timezone, timedelta


# ============================================================
# 設定
# ============================================================

# 期間
PERIODS = ["1m", "6m", "5y"]


# ============================================================
# 1. 銘柄リスト
# ============================================================

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


print(
    "取得する銘柄数:",
    len(tickers)
)


# ============================================================
# 2. 株価取得
# ============================================================

# 5年間の日足を取得
#
# ここから
# ・1か月 → 日足
# ・半年 → 週足
# ・5年 → 月足
# を作る
#
data = yf.download(
    tickers,
    period="5y",
    interval="1d",
    group_by="ticker",
    threads=True
)


# ============================================================
# 3. 補助関数
# ============================================================

def get_prices_for_ticker(
    data,
    ticker
):
    """
    yfinanceの結果から
    1銘柄のCloseだけを取り出す
    """

    try:

        prices = (
            data[ticker]["Close"]
            .dropna()
            .copy()
        )

        if prices.empty:
            return None

        prices.index = pd.to_datetime(
            prices.index
        )

        return prices

    except Exception as e:

        print(
            f"{ticker}: Close取得エラー {e}"
        )

        return None


def get_period_start(
    prices,
    months=None,
    years=None
):
    """
    指定期間の最初の日付を返す
    """

    last_date = prices.index[-1]

    if months is not None:

        start_date = (
            last_date
            - pd.DateOffset(months=months)
        )

    elif years is not None:

        start_date = (
            last_date
            - pd.DateOffset(years=years)
        )

    else:

        start_date = prices.index[0]

    return start_date


def normalize_prices(
    prices,
    base_price
):
    """
    指定した基準価格を100として正規化
    """

    result = []

    for date, price in prices.items():

        value = (
            float(price)
            / float(base_price)
            * 100
        )

        result.append({

            "date":
                pd.Timestamp(date).strftime(
                    "%Y/%m/%d"
                ),

            "value":
                round(
                    value,
                    2
                )

        })

    return result


def make_period_data(
    prices
):
    """
    1か月、半年、5年のデータを作る。

    戻り値：

    {
        "1m": {
            "change_percent": ...,
            "history": [...]
        },

        "6m": {
            "change_percent": ...,
            "history": [...]
        },

        "5y": {
            "change_percent": ...,
            "history": [...]
        },

        "from_1m_6m": {
            "history": [...]
        },

        "from_1m_5y": {
            "history": [...]
        },

        "from_6m_5y": {
            "history": [...]
        }
    }
    """

    last_date = prices.index[-1]


    # --------------------------------------------------------
    # 1か月
    # --------------------------------------------------------

    start_1m = (
        last_date
        - pd.DateOffset(months=1)
    )

    prices_1m = prices[
        prices.index >= start_1m
    ]

    if len(prices_1m) < 2:

        return None


    base_1m = float(
        prices_1m.iloc[0]
    )

    current_price = float(
        prices.iloc[-1]
    )

    change_1m = (
        (
            current_price
            - base_1m
        )
        / base_1m
        * 100
    )


    history_1m =
        normalize_prices(
            prices_1m,
            base_1m
        )


    # --------------------------------------------------------
    # 半年
    # --------------------------------------------------------

    start_6m = (
        last_date
        - pd.DateOffset(months=6)
    )

    prices_6m = prices[
        prices.index >= start_6m
    ]

    if len(prices_6m) < 2:

        return None


    base_6m = float(
        prices_6m.iloc[0]
    )


    change_6m = (
        (
            current_price
            - base_6m
        )
        / base_6m
        * 100
    )


    # 半年は週末ごとにまとめる
    weekly_6m = (
        prices_6m
        .resample("W-FRI")
        .last()
        .dropna()
    )


    history_6m =
        normalize_prices(
            weekly_6m,
            base_6m
        )


    # --------------------------------------------------------
    # 5年
    # --------------------------------------------------------

    start_5y = (
        last_date
        - pd.DateOffset(years=5)
    )

    prices_5y = prices[
        prices.index >= start_5y
    ]

    if len(prices_5y) < 2:

        return None


    base_5y = float(
        prices_5y.iloc[0]
    )


    change_5y = (
        (
            current_price
            - base_5y
        )
        / base_5y
        * 100
    )


    # 5年は月末ごとにまとめる
    monthly_5y = (
        prices_5y
        .resample("ME")
        .last()
        .dropna()
    )


    # 最後の現在値を追加
    if (
        len(monthly_5y) == 0
        or monthly_5y.index[-1]
        < prices_5y.index[-1]
    ):

        monthly_5y = pd.concat([
            monthly_5y,
            prices_5y.iloc[[-1]]
        ])


    history_5y =
        normalize_prices(
            monthly_5y,
            base_5y
        )


    # --------------------------------------------------------
    # 1か月前を100にしたまま半年を見る
    # --------------------------------------------------------

    weekly_6m_from_1m = (
        prices_6m
        .resample("W-FRI")
        .last()
        .dropna()
    )


    history_1m_6m =
        normalize_prices(
            weekly_6m_from_1m,
            base_1m
        )


    # --------------------------------------------------------
    # 1か月前を100にしたまま5年を見る
    # --------------------------------------------------------

    monthly_5y_from_1m = (
        prices_5y
        .resample("ME")
        .last()
        .dropna()
    )


    if (
        len(monthly_5y_from_1m) == 0
        or monthly_5y_from_1m.index[-1]
        < prices_5y.index[-1]
    ):

        monthly_5y_from_1m = pd.concat([
            monthly_5y_from_1m,
            prices_5y.iloc[[-1]]
        ])


    history_1m_5y =
        normalize_prices(
            monthly_5y_from_1m,
            base_1m
        )


    # --------------------------------------------------------
    # 半年前を100にしたまま5年を見る
    # --------------------------------------------------------

    monthly_5y_from_6m = (
        prices_5y
        .resample("ME")
        .last()
        .dropna()
    )


    if (
        len(monthly_5y_from_6m) == 0
        or monthly_5y_from_6m.index[-1]
        < prices_5y.index[-1]
    ):

        monthly_5y_from_6m = pd.concat([
            monthly_5y_from_6m,
            prices_5y.iloc[[-1]]
        ])


    history_6m_5y =
        normalize_prices(
            monthly_5y_from_6m,
            base_6m
        )


    return {

        "1m": {

            "change_percent":
                round(
                    change_1m,
                    2
                ),

            "history":
                history_1m

        },

        "6m": {

            "change_percent":
                round(
                    change_6m,
                    2
                ),

            "history":
                history_6m

        },

        "5y": {

            "change_percent":
                round(
                    change_5y,
                    2
                ),

            "history":
                history_5y

        },

        "from_1m_6m": {

            "history":
                history_1m_6m

        },

        "from_1m_5y": {

            "history":
                history_1m_5y

        },

        "from_6m_5y": {

            "history":
                history_6m_5y

        }

    }


def get_themes(stock):

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


    # 重複削除
    themes = list(
        dict.fromkeys(themes)
    )

    return themes


def make_average_history(
    stock_items
):
    """
    複数銘柄のhistoryを平均する
    """

    if not stock_items:
        return []


    all_records = []


    for stock in stock_items:

        history =
            stock.get(
                "history",
                []
            )

        for point in history:

            all_records.append({

                "date":
                    point["date"],

                "value":
                    point["value"]

            })


    if not all_records:
        return []


    df = pd.DataFrame(
        all_records
    )


    result = (
        df
        .groupby("date")["value"]
        .mean()
        .reset_index()
    )


    result = result.sort_values(
        "date"
    )


    return [

        {

            "date":
                row["date"],

            "value":
                round(
                    float(row["value"]),
                    2
                )

        }

        for _, row in result.iterrows()

    ]


# ============================================================
# 4. 各銘柄のデータ作成
# ============================================================

stock_data_all = {}

valid_stock_rows = []


for _, stock in stocks.iterrows():

    code = stock["code"]

    ticker = f"{code}.T"


    try:

        prices =
            get_prices_for_ticker(
                data,
                ticker
            )


        if prices is None:

            print(
                f"{ticker}: データなし"
            )

            continue


        if len(prices) < 20:

            print(
                f"{ticker}: データ不足"
            )

            continue


        period_data =
            make_period_data(
                prices
            )


        if period_data is None:

            print(
                f"{ticker}: 期間データ作成失敗"
            )

            continue


        current_price =
            round(
                float(
                    prices.iloc[-1]
                ),
                2
            )


        stock_data_all[code] = {

            "code":
                code,

            "name":
                stock["name"],

            "industry":
                stock["industry"],

            "themes":
                get_themes(stock),

            "price":
                current_price,

            "periods":
                period_data

        }


        valid_stock_rows.append(
            stock
        )


        print(
            f"{ticker}: OK"
        )


    except Exception as e:

        print(
            f"{ticker}: エラー {e}"
        )


print(
    "正常取得銘柄数:",
    len(stock_data_all)
)


# ============================================================
# 5. 期間ごとの業界・テーマランキングを作る関数
# ============================================================

def build_period_dataset(
    period
):

    # --------------------------------------------------------
    # 銘柄ランキング用
    # --------------------------------------------------------

    stock_items = []


    for code, item in (
        stock_data_all.items()
    ):

        pdata =
            item["periods"][period]


        stock_items.append({

            "code":
                code,

            "name":
                item["name"],

            "industry":
                item["industry"],

            "price":
                item["price"],

            "change_percent":
                pdata["change_percent"],

            "history":
                pdata["history"]

        })


    # --------------------------------------------------------
    # 業界ランキング
    # --------------------------------------------------------

    industry_groups = {}


    for stock in stock_items:

        industry =
            stock["industry"]


        if industry not in industry_groups:

            industry_groups[industry] = []


        industry_groups[industry].append(
            stock
        )


    industries = []


    for industry, group in (
        industry_groups.items()
    ):

        avg =
            sum(
                x["change_percent"]
                for x in group
            ) / len(group)


        industries.append({

            "industry":
                industry,

            "change_percent":
                round(
                    avg,
                    2
                )

        })


    industries.sort(
        key=lambda x:
            x["change_percent"],
        reverse=True
    )


    # --------------------------------------------------------
    # 業界TOP10グラフ
    # --------------------------------------------------------

    top_industry_names = [

        x["industry"]

        for x in industries[:10]

    ]


    top_industries = []


    for industry in top_industry_names:

        group =
            industry_groups[
                industry
            ]


        history = []


        dates = set()


        for stock in group:

            for point in stock["history"]:

                dates.add(
                    point["date"]
                )


        for date in sorted(dates):

            values = []


            for stock in group:

                for point in stock["history"]:

                    if point["date"] == date:

                        values.append(
                            point["value"]
                        )

                        break


            if values:

                history.append({

                    "date":
                        date,

                    "value":
                        round(
                            sum(values)
                            / len(values),
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

            "industry":
                industry,

            "change_percent":
                change,

            "history":
                history

        })


    # --------------------------------------------------------
    # 業界別銘柄
    # --------------------------------------------------------

    industry_stocks = {}


    for industry, group in (
        industry_groups.items()
    ):

        sorted_group = sorted(

            group,

            key=lambda x:
                x["change_percent"],

            reverse=True

        )


        industry_stocks[industry] = (
            sorted_group
        )


    # --------------------------------------------------------
    # テーマ
    # --------------------------------------------------------

    theme_groups = {}


    for stock in stock_items:

        original =
            stock_data_all[
                stock["code"]
            ]


        for theme in original["themes"]:

            if theme not in theme_groups:

                theme_groups[theme] = []


            theme_groups[theme].append(
                stock
            )


    themes = []


    for theme, group in (
        theme_groups.items()
    ):

        avg =
            sum(
                x["change_percent"]
                for x in group
            ) / len(group)


        themes.append({

            "theme":
                theme,

            "change_percent":
                round(
                    avg,
                    2
                )

        })


    themes.sort(

        key=lambda x:
            x["change_percent"],

        reverse=True

    )


    # --------------------------------------------------------
    # テーマTOP10
    # --------------------------------------------------------

    top_theme_names = [

        x["theme"]

        for x in themes[:10]

    ]


    top_themes = []


    for theme in top_theme_names:

        group =
            theme_groups[
                theme
            ]


        history = []


        dates = set()


        for stock in group:

            for point in stock["history"]:

                dates.add(
                    point["date"]
                )


        for date in sorted(dates):

            values = []


            for stock in group:

                for point in stock["history"]:

                    if point["date"] == date:

                        values.append(
                            point["value"]
                        )

                        break


            if values:

                history.append({

                    "date":
                        date,

                    "value":
                        round(
                            sum(values)
                            / len(values),
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

            "theme":
                theme,

            "change_percent":
                change,

            "history":
                history

        })


    # --------------------------------------------------------
    # テーマ別銘柄
    # --------------------------------------------------------

    theme_stocks = {}


    for theme, group in (
        theme_groups.items()
    ):

        theme_stocks[theme] = sorted(

            group,

            key=lambda x:
                x["change_percent"],

            reverse=True

        )


    # --------------------------------------------------------
    # 値上がり銘柄TOP10
    # --------------------------------------------------------

    top_gainers = sorted(

        stock_items,

        key=lambda x:
            x["change_percent"],

        reverse=True

    )[:10]


    return {

        "industries":
            industries,

        "top_industries":
            top_industries,

        "industry_stocks":
            industry_stocks,

        "themes":
            themes,

        "top_themes":
            top_themes,

        "theme_stocks":
            theme_stocks,

        "top_gainers":
            top_gainers

    }


# ============================================================
# 6. 期間別データを作成
# ============================================================

print(
    "期間別データを作成しています..."
)


dataset_1m =
    build_period_dataset(
        "1m"
    )


dataset_6m =
    build_period_dataset(
        "6m"
    )


dataset_5y =
    build_period_dataset(
        "5y"
    )


# ============================================================
# 7. 詳細グラフ用の追加履歴を各銘柄に付ける
# ============================================================

for code, item in (
    stock_data_all.items()
):

    p = item["periods"]


    # 1か月基準 → 半年
    p["from_1m_6m"] =
        item["periods"][
            "from_1m_6m"
        ]


    # 1か月基準 → 5年
    p["from_1m_5y"] =
        item["periods"][
            "from_1m_5y"
        ]


    # 半年基準 → 5年
    p["from_6m_5y"] =
        item["periods"][
            "from_6m_5y"
        ]


# ============================================================
# 8. 業界・テーマ銘柄の詳細データに
#    5年分の履歴を含める
# ============================================================

def add_detail_histories(
    dataset
):

    for section_name in [
        "industry_stocks",
        "theme_stocks"
    ]:

        groups =
            dataset[section_name]


        for group_name, group in (
            groups.items()
        ):

            for stock in group:

                code =
                    stock["code"]


                if code not in stock_data_all:
                    continue


                periods =
                    stock_data_all[
                        code
                    ]["periods"]


                stock["periods"] = periods


# 各期間について追加
add_detail_histories(
    dataset_1m
)

add_detail_histories(
    dataset_6m
)

add_detail_histories(
    dataset_5y
)


# ============================================================
# 9. JSON
# ============================================================

jst = timezone(
    timedelta(hours=9)
)


output = {

    "updated_at":
        datetime.now(jst).strftime(
            "%Y-%m-%d %H:%M"
        ),


    # --------------------------------------------------------
    # 1か月
    # --------------------------------------------------------

    "1m":
        dataset_1m,


    # --------------------------------------------------------
    # 半年
    # --------------------------------------------------------

    "6m":
        dataset_6m,


    # --------------------------------------------------------
    # 5年
    # --------------------------------------------------------

    "5y":
        dataset_5y

}


# ============================================================
# 10. data.json保存
# ============================================================

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

print(
    "1か月・半年・5年のデータを保存しました"
)
```
