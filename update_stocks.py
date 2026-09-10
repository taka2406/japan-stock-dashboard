import pandas as pd
import yfinance as yf
import json
from datetime import datetime, timezone, timedelta


# ============================================================
# 設定
# ============================================================

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

print("取得する銘柄数:", len(tickers))


# ============================================================
# 2. 株価取得
# ============================================================

print("株価データを取得しています...")

# ------------------------------------------------------------
# 日本時間
# ------------------------------------------------------------

JST = timezone(timedelta(hours=9))
now_jst = datetime.now(JST)

# ------------------------------------------------------------
# 更新モード
#
# GitHub Actionsから UPDATE_MODE を渡す。
#
# intraday → 11時更新：当日11時時点の現在値
# close    → 16時更新：当日の終値
#
# 手動実行などで指定がない場合は、時刻から自動判定する。
# ------------------------------------------------------------

import os

SNAPSHOT_MODE = os.environ.get("UPDATE_MODE", "").strip().lower()

if SNAPSHOT_MODE not in ("intraday", "close"):

    # 13時より前なら11時更新、それ以外は終値更新
    SNAPSHOT_MODE = (
        "intraday"
        if now_jst.hour < 13
        else "close"
    )

print(
    "現在時刻:",
    now_jst.strftime("%Y-%m-%d %H:%M:%S")
)

print(
    "更新モード:",
    SNAPSHOT_MODE
)

# ------------------------------------------------------------
# 5年間の日足終値
#
# 過去のグラフは、この日足終値を基本データにする。
# 11時更新時だけ、今日のデータを11時現在値へ差し替える。
# 16時更新時は、今日も終値を使用する。
# ------------------------------------------------------------

daily_data = yf.download(
    tickers,
    period="5y",
    interval="1d",
    group_by="ticker",
    threads=True,
    auto_adjust=False,
    progress=False
)

# ------------------------------------------------------------
# 当日の5分足
#
# 11時現在値の取得に使用する。
# 16時に日足の当日終値がまだ配信されていない場合は、
# 当日最後の5分足をバックアップとして使用する。
# ------------------------------------------------------------

intraday_data = yf.download(
    tickers,
    period="1d",
    interval="5m",
    group_by="ticker",
    threads=True,
    auto_adjust=False,
    progress=False
)


# ============================================================
# 3. 補助関数
# ============================================================

def get_prices_for_ticker(data, ticker):
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

        prices.index = pd.to_datetime(prices.index)

        return prices

    except Exception as e:
        print(f"{ticker}: Close取得エラー {e}")
        return None


def get_today_intraday_price(
    intraday_data,
    ticker,
    target_time
):
    """
    当日の5分足から、target_time以前で最新のCloseを取得する。

    11:00更新なら11:00以前の最新5分足を使用する。
    例えば11:00の実行時には10:55の5分足Closeが対象になる。
    """

    try:

        prices = (
            intraday_data[ticker]["Close"]
            .dropna()
            .copy()
        )

        if prices.empty:
            return None

        prices.index = pd.to_datetime(prices.index)

        # yfinanceのインデックスを日本時間のnaive Timestampへ統一
        if prices.index.tz is not None:
            prices.index = (
                prices.index
                .tz_convert("Asia/Tokyo")
                .tz_localize(None)
            )
        else:
            # yfinance側でUTCのnaive indexとして返るケースに対応
            prices.index = (
                prices.index
                .tz_localize("UTC")
                .tz_convert("Asia/Tokyo")
                .tz_localize(None)
            )

        today = target_time.date()

        prices_today = prices[
            prices.index.date == today
        ]

        if prices_today.empty:
            return None

        prices_today = prices_today[
            prices_today.index <= target_time
        ]

        if prices_today.empty:
            return None

        return float(prices_today.iloc[-1])

    except Exception as e:

        print(
            f"{ticker}: 当日現在値取得エラー {e}"
        )

        return None


def get_today_close_from_intraday(
    intraday_data,
    ticker,
    target_time
):
    """
    当日の5分足から、15:30までに存在する最後のCloseを取得する。

    16時時点で日足の当日終値がyfinanceからまだ返ってこない場合の
    バックアップとして使用する。
    """

    try:

        prices = (
            intraday_data[ticker]["Close"]
            .dropna()
            .copy()
        )

        if prices.empty:
            return None

        prices.index = pd.to_datetime(prices.index)

        if prices.index.tz is not None:
            prices.index = (
                prices.index
                .tz_convert("Asia/Tokyo")
                .tz_localize(None)
            )
        else:
            prices.index = (
                prices.index
                .tz_localize("UTC")
                .tz_convert("Asia/Tokyo")
                .tz_localize(None)
            )

        today = target_time.date()
        close_time = target_time.replace(
            hour=15,
            minute=30,
            second=0,
            microsecond=0
        )

        prices_today = prices[
            (prices.index.date == today)
            & (prices.index <= close_time)
        ]

        if prices_today.empty:
            return None

        return float(prices_today.iloc[-1])

    except Exception as e:

        print(
            f"{ticker}: 当日終値バックアップ取得エラー {e}"
        )

        return None


def add_today_snapshot(
    daily_prices,
    snapshot_price,
    snapshot_datetime
):
    """
    日足終値データに今日のスナップショットを追加する。

    過去    → 終値
    今日    → 11時現在値 または 終値

    今日の日足がすでに存在する場合は、今日の値を差し替える。
    """

    if (
        daily_prices is None
        or daily_prices.empty
        or snapshot_price is None
    ):
        return daily_prices

    prices = daily_prices.copy()

    today = snapshot_datetime.date()

    # 今日の日足があれば一度削除
    today_mask = prices.index.date == today

    prices = prices[~today_mask]

    # 今日のスナップショットを日付ラベルで追加
    new_row = pd.Series(
        [float(snapshot_price)],
        index=[pd.Timestamp(today)]
    )

    prices = pd.concat([
        prices,
        new_row
    ])

    prices = prices.sort_index()

    return prices


def get_first_price(prices):
    """
    最初に存在する価格を取得
    """

    if prices is None or prices.empty:
        return None

    return float(prices.iloc[0])


def normalize_prices(prices, base_price):
    """
    指定した基準価格を100として正規化
    """

    if prices is None or prices.empty:
        return []

    if base_price is None or base_price == 0:
        return []

    result = []

    for date, price in prices.items():

        value = (
            float(price)
            / float(base_price)
            * 100
        )

        result.append({
            "date": pd.Timestamp(date).strftime("%Y/%m/%d"),
            "value": round(value, 2)
        })

    return result


def add_base_point(history, base_date, base_price):
    """
    グラフの先頭に「基準価格=100」の点を追加する。

    週足・月足では期間開始日と最初の集計日の間に
    ずれが生じるため、そのずれを補正する。
    """

    if base_date is None or base_price is None:
        return history

    base_point = {
        "date": pd.Timestamp(base_date).strftime("%Y/%m/%d"),
        "value": 100.0
    }

    if not history:
        return [base_point]

    # すでに同じ日付があれば100にする
    for point in history:
        if point["date"] == base_point["date"]:
            point["value"] = 100.0
            return history

    return [base_point] + history


def make_period_data(prices):
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

    if prices is None or len(prices) < 2:
        return None

    last_date = prices.index[-1]
    current_price = float(prices.iloc[-1])

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

    base_1m = get_first_price(prices_1m)
    base_date_1m = prices_1m.index[0]

    if base_1m is None or base_1m == 0:
        return None

    change_1m = (
        (
            current_price - base_1m
        )
        / base_1m
        * 100
    )

    history_1m = normalize_prices(
        prices_1m,
        base_1m
    )

    history_1m = add_base_point(
        history_1m,
        base_date_1m,
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

    base_6m = get_first_price(prices_6m)
    base_date_6m = prices_6m.index[0]

    if base_6m is None or base_6m == 0:
        return None

    change_6m = (
        (
            current_price - base_6m
        )
        / base_6m
        * 100
    )

    # 半年は週足
    weekly_6m = (
        prices_6m
        .resample("W-FRI")
        .last()
        .dropna()
    )

    history_6m = normalize_prices(
        weekly_6m,
        base_6m
    )

    history_6m = add_base_point(
        history_6m,
        base_date_6m,
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

    base_5y = get_first_price(prices_5y)
    base_date_5y = prices_5y.index[0]

    if base_5y is None or base_5y == 0:
        return None

    change_5y = (
        (
            current_price - base_5y
        )
        / base_5y
        * 100
    )

    # 5年は月足
    monthly_5y = (
        prices_5y
        .resample("ME")
        .last()
        .dropna()
    )

    # 現在値を最後に追加
    if (
        len(monthly_5y) == 0
        or monthly_5y.index[-1] < prices_5y.index[-1]
    ):
        monthly_5y = pd.concat([
            monthly_5y,
            prices_5y.iloc[[-1]]
        ])

    history_5y = normalize_prices(
        monthly_5y,
        base_5y
    )

    history_5y = add_base_point(
        history_5y,
        base_date_5y,
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

    history_1m_6m = normalize_prices(
        weekly_6m_from_1m,
        base_1m
    )

    history_1m_6m = add_base_point(
        history_1m_6m,
        base_date_1m,
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
        or monthly_5y_from_1m.index[-1] < prices_5y.index[-1]
    ):
        monthly_5y_from_1m = pd.concat([
            monthly_5y_from_1m,
            prices_5y.iloc[[-1]]
        ])

    history_1m_5y = normalize_prices(
        monthly_5y_from_1m,
        base_1m
    )

    history_1m_5y = add_base_point(
        history_1m_5y,
        base_date_1m,
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
        or monthly_5y_from_6m.index[-1] < prices_5y.index[-1]
    ):
        monthly_5y_from_6m = pd.concat([
            monthly_5y_from_6m,
            prices_5y.iloc[[-1]]
        ])

    history_6m_5y = normalize_prices(
        monthly_5y_from_6m,
        base_6m
    )

    history_6m_5y = add_base_point(
        history_6m_5y,
        base_date_6m,
        base_6m
    )

    return {
        "1m": {
            "change_percent": round(
                change_1m,
                2
            ),
            "history": history_1m
        },

        "6m": {
            "change_percent": round(
                change_6m,
                2
            ),
            "history": history_6m
        },

        "5y": {
            "change_percent": round(
                change_5y,
                2
            ),
            "history": history_5y
        },

        "from_1m_6m": {
            "history": history_1m_6m
        },

        "from_1m_5y": {
            "history": history_1m_5y
        },

        "from_6m_5y": {
            "history": history_6m_5y
        }
    }


def get_themes(stock):
    """
    1銘柄につき最大3テーマを取得
    """

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


def make_average_history(stock_items):
    """
    複数銘柄のhistoryを平均する
    """

    if not stock_items:
        return []

    all_records = []

    for stock in stock_items:

        history = stock.get(
            "history",
            []
        )

        for point in history:

            all_records.append({
                "date": point["date"],
                "value": point["value"]
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
            "date": row["date"],
            "value": round(
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

print("各銘柄のデータを作成しています...")

for _, stock in stocks.iterrows():

    code = stock["code"]
    ticker = f"{code}.T"

    try:

        # ----------------------------------------------------
        # 過去5年間の日足終値
        # ----------------------------------------------------

        prices = get_prices_for_ticker(
            daily_data,
            ticker
        )

        if prices is None:

            print(
                f"{ticker}: 日足データなし"
            )

            continue

        if len(prices) < 20:

            print(
                f"{ticker}: データ不足"
            )

            continue

        # ----------------------------------------------------
        # 今日の価格を決定
        # ----------------------------------------------------

        snapshot_time = now_jst.replace(
            tzinfo=None
        )

        today = snapshot_time.date()

        today_snapshot_price = None

        # ====================================================
        # 11時更新
        # ====================================================

        if SNAPSHOT_MODE == "intraday":

            today_snapshot_price = get_today_intraday_price(
                intraday_data,
                ticker,
                snapshot_time.replace(
                    hour=11,
                    minute=0,
                    second=0,
                    microsecond=0
                )
            )

            if today_snapshot_price is None:

                print(
                    f"{ticker}: 11時現在値取得失敗"
                    " → 最新終値を使用"
                )

                today_snapshot_price = float(
                    prices.iloc[-1]
                )

        # ====================================================
        # 16時更新
        # ====================================================

        else:

            # まず当日の日足終値を探す
            today_prices = prices[
                prices.index.date == today
            ]

            if not today_prices.empty:

                today_snapshot_price = float(
                    today_prices.iloc[-1]
                )

            else:

                # 日足更新がまだの場合は、当日最後の5分足を
                # 15:30までの範囲でバックアップとして使用
                today_snapshot_price = get_today_close_from_intraday(
                    intraday_data,
                    ticker,
                    snapshot_time
                )

            if today_snapshot_price is None:

                print(
                    f"{ticker}: 本日終値取得失敗"
                    " → 最新日足終値を使用"
                )

                today_snapshot_price = float(
                    prices.iloc[-1]
                )

        # ----------------------------------------------------
        # 今日の値を日足データへ追加
        #
        # 11時：過去終値 + 今日11時現在値
        # 16時：過去終値 + 今日終値
        # ----------------------------------------------------

        prices_for_dashboard = add_today_snapshot(
            prices,
            today_snapshot_price,
            snapshot_time
        )

        # ----------------------------------------------------
        # 期間データ作成
        # ----------------------------------------------------

        period_data = make_period_data(
            prices_for_dashboard
        )

        if period_data is None:

            print(
                f"{ticker}: 期間データ作成失敗"
            )

            continue

        # ----------------------------------------------------
        # 現在価格
        # ----------------------------------------------------

        current_price = round(
            float(today_snapshot_price),
            2
        )

        stock_data_all[code] = {

            "code": code,

            "name": stock["name"],

            "industry": stock["industry"],

            "themes": get_themes(stock),

            "price": current_price,

            "price_type": (
                "intraday"
                if SNAPSHOT_MODE == "intraday"
                else "close"
            ),

            "snapshot_at": now_jst.strftime(
                "%Y-%m-%d %H:%M"
            ),

            "periods": period_data

        }

        print(
            f"{ticker}: OK "
            f"price={current_price} "
            f"type={SNAPSHOT_MODE}"
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

def build_period_dataset(period):

    # --------------------------------------------------------
    # 銘柄ランキング用
    # --------------------------------------------------------

    stock_items = []

    for code, item in stock_data_all.items():

        pdata = item["periods"][period]

        stock_items.append({

            "code": code,

            "name": item["name"],

            "industry": item["industry"],

            "price": item["price"],

            "change_percent": pdata["change_percent"],

            "history": pdata["history"]

        })

    # --------------------------------------------------------
    # 業界ランキング
    # --------------------------------------------------------

    industry_groups = {}

    for stock in stock_items:

        industry = stock["industry"]

        if industry not in industry_groups:
            industry_groups[industry] = []

        industry_groups[industry].append(
            stock
        )

    industries = []

    for industry, group in industry_groups.items():

        avg = (
            sum(
                x["change_percent"]
                for x in group
            )
            / len(group)
        )

        industries.append({

            "industry": industry,

            "change_percent": round(
                avg,
                2
            )

        })

    industries.sort(
        key=lambda x: x["change_percent"],
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

        group = industry_groups[
            industry
        ]

        history = make_average_history(
            group
        )

        change = next(
            (
                x["change_percent"]
                for x in industries
                if x["industry"] == industry
            ),
            0
        )

        top_industries.append({

            "industry": industry,

            "change_percent": change,

            "history": history

        })

    # --------------------------------------------------------
    # 業界別銘柄
    # --------------------------------------------------------

    industry_stocks = {}

    for industry, group in industry_groups.items():

        sorted_group = sorted(
            group,
            key=lambda x: x["change_percent"],
            reverse=True
        )

        industry_stocks[industry] = sorted_group

    # --------------------------------------------------------
    # テーマ
    # --------------------------------------------------------

    theme_groups = {}

    for stock in stock_items:

        original = stock_data_all[
            stock["code"]
        ]

        for theme in original["themes"]:

            if theme not in theme_groups:
                theme_groups[theme] = []

            theme_groups[theme].append(
                stock
            )

    themes = []

    for theme, group in theme_groups.items():

        avg = (
            sum(
                x["change_percent"]
                for x in group
            )
            / len(group)
        )

        themes.append({

            "theme": theme,

            "change_percent": round(
                avg,
                2
            )

        })

    themes.sort(
        key=lambda x: x["change_percent"],
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

        group = theme_groups[
            theme
        ]

        history = make_average_history(
            group
        )

        change = next(
            (
                x["change_percent"]
                for x in themes
                if x["theme"] == theme
            ),
            0
        )

        top_themes.append({

            "theme": theme,

            "change_percent": change,

            "history": history

        })

    # --------------------------------------------------------
    # テーマ別銘柄
    # --------------------------------------------------------

    theme_stocks = {}

    for theme, group in theme_groups.items():

        theme_stocks[theme] = sorted(
            group,
            key=lambda x: x["change_percent"],
            reverse=True
        )

    # --------------------------------------------------------
    # 値上がり銘柄TOP10
    # --------------------------------------------------------

    top_gainers = sorted(
        stock_items,
        key=lambda x: x["change_percent"],
        reverse=True
    )[:10]

    # --------------------------------------------------------
    # 値下がり銘柄TOP10
    # --------------------------------------------------------

    top_losers = sorted(
        stock_items,
        key=lambda x: x["change_percent"]
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
            top_gainers,

        "top_losers":
            top_losers

    }


# ============================================================
# 6. 期間別データを作成
# ============================================================

print(
    "期間別データを作成しています..."
)

dataset_1m = build_period_dataset(
    "1m"
)

dataset_6m = build_period_dataset(
    "6m"
)

dataset_5y = build_period_dataset(
    "5y"
)


# ============================================================
# 7. 詳細グラフ用の追加履歴を各銘柄に付ける
# ============================================================

def add_detail_histories(dataset):

    for section_name in [
        "industry_stocks",
        "theme_stocks"
    ]:

        groups = dataset[section_name]

        for group_name, group in groups.items():

            for stock in group:

                code = stock["code"]

                if code not in stock_data_all:
                    continue

                periods = stock_data_all[
                    code
                ]["periods"]

                stock["periods"] = periods


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
# 8. JSON
# ============================================================

jst = timezone(
    timedelta(hours=9)
)

output = {

    "updated_at":
        now_jst.strftime(
            "%Y-%m-%d %H:%M"
        ),

    "price_mode":
        SNAPSHOT_MODE,

    "price_mode_label":
        (
            "11時現在値"
            if SNAPSHOT_MODE == "intraday"
            else "終値"
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
# 9. data.json保存
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
