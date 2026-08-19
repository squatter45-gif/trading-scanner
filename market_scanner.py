#!/usr/bin/env python3
"""
Dual-Market Trading Scanner - BoxRunner Scorecard Format
Runs at 7 AM (Australian market) and 7 PM (US market)
Outputs: BoxRunner-compatible scorecards (mid-caps + mega-caps separate)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import json
import os
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict

# ============================================================================
# CONFIGURATION
# ============================================================================

# Market definitions
MARKETS = {
    'ASX': {
        'timezone': 'Australia/Sydney',
        'market_open': 10,  # 10 AM Sydney time
        'tickers': {
            'megacap': ['CBA', 'BHP', 'CSL', 'WBC', 'ANZ', 'NAB', 'MQG', 'TLS', 'AMP', 'APD'],
            'midcap': ['APA', 'AGL', 'AWC', 'AZJ', 'BAP', 'GMG', 'IAG', 'LLC', 'ORA', 'REA']
        }
    },
    'US': {
        'timezone': 'America/New_York',
        'market_open': 9,  # 9:30 AM ET (market opens, we run at 9:35 PM previous)
        'tickers': {
            'megacap': ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'GOOGL', 'AMZN', 'META', 'BRK.B', 'NFLX', 'MSTR'],
            'midcap': ['SNDK', 'MARA', 'UPST', 'DKNG', 'COIN', 'SQ', 'PYPL', 'ROKU', 'CRWD', 'MDB']
        }
    }
}

# Screening thresholds
VOLUME_THRESHOLD = 10_000_000  # Min avg daily volume
TREND_LOOKBACK = 30  # Days for trend analysis
MIN_TREND_PCT = 3.0  # Min 3% gain over trend period
SCORE_MAX = 50  # BoxRunner uses 50-point scale

# ============================================================================
# SCORECARD DATA CLASS
# ============================================================================

@dataclass
class Scorecard:
    """BoxRunner-compatible scorecard"""
    ticker: str
    price: float
    price_change_pct: float
    trend: str  # 'Up', 'Down', 'Neutral'
    status: str  # 'Broken out', 'Inside box', 'Building support'
    support: float
    resistance: float
    buy_above: float
    stop: float
    score: int  # 0-50
    volume_pct: float  # vs average
    setup_note: str
    scan_time: str
    market: str  # 'ASX' or 'US'
    category: str  # 'megacap' or 'midcap'

    def to_dict(self):
        """Convert to dictionary for JSON/CSV export"""
        return asdict(self)

# ============================================================================
# SCANNER CLASS
# ============================================================================

class MarketScanner:
    """Scan multiple markets and generate BoxRunner scorecards"""

    def __init__(self, market: str, category: str):
        self.market = market
        self.category = category
        self.config = MARKETS[market]
        self.tickers = self.config['tickers'][category]
        self.scorecards = []
        self.scan_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def fetch_data(self, ticker: str, period: str = '60d') -> pd.DataFrame:
        """Fetch OHLCV data for ticker"""
        try:
            data = yf.download(ticker, period=period, progress=False)
            return data
        except Exception as e:
            print(f"  ❌ Error fetching {ticker}: {e}")
            return None

    def calculate_trend(self, data: pd.DataFrame) -> Tuple[str, float]:
        """Calculate trend direction and strength"""
        if data is None or len(data) < TREND_LOOKBACK:
            return 'Neutral', 0.0

        past_price = data['Close'].iloc[-TREND_LOOKBACK]
        current_price = data['Close'].iloc[-1]
        trend_pct = ((current_price - past_price) / past_price) * 100

        if trend_pct >= MIN_TREND_PCT:
            trend = 'Up'
        elif trend_pct <= -MIN_TREND_PCT:
            trend = 'Down'
        else:
            trend = 'Neutral'

        return trend, trend_pct

    def calculate_support_resistance(self, data: pd.DataFrame, lookback: int = 20) -> Tuple[float, float]:
        """Calculate support and resistance levels (20-day range)"""
        if data is None or len(data) < lookback:
            return 0.0, 0.0

        recent = data.iloc[-lookback:]
        support = recent['Low'].min()
        resistance = recent['High'].max()

        return support, resistance

    def calculate_volume_metric(self, data: pd.DataFrame, lookback: int = 20) -> float:
        """Calculate current volume vs average"""
        if data is None or len(data) < lookback:
            return 0.0

        avg_volume = data['Volume'].iloc[-lookback:-1].mean()
        current_volume = data['Volume'].iloc[-1]

        if avg_volume == 0:
            return 0.0

        return (current_volume / avg_volume) * 100

    def score_setup(self, data: pd.DataFrame, trend: str, trend_pct: float,
                   volume_pct: float) -> Tuple[int, str]:
        """
        Score setup 0-50 based on:
        - Trend strength (0-20 points)
        - Volume confirmation (0-15 points)
        - Price structure (0-15 points)
        """
        score = 0

        # Trend scoring (0-20)
        if trend == 'Up':
            score += 15
            if trend_pct >= 10:
                score += 5
        elif trend == 'Down':
            score += 0
        else:
            score += 5

        # Volume scoring (0-15)
        if volume_pct >= 150:
            score += 15
        elif volume_pct >= 120:
            score += 10
        elif volume_pct >= 100:
            score += 5

        # Determine status and note
        if trend == 'Up' and volume_pct >= 120:
            status = 'Broken out'
            note = f'Strong uptrend, above-average volume'
        elif trend == 'Up' and volume_pct < 120:
            status = 'Building support'
            note = f'Uptrend forming, watch volume'
        elif trend == 'Down':
            status = 'Inside box'
            note = f'Downtrend in place, avoid'
        else:
            status = 'Inside box'
            note = 'Consolidating, neutral setup'

        return score, status, note

    def scan_ticker(self, ticker: str) -> Scorecard:
        """Scan single ticker and generate scorecard"""
        print(f"  Scanning {ticker}...", end=" ")

        # Fetch data
        data = self.fetch_data(ticker)
        if data is None or data.empty:
            print("❌ (no data)")
            return None

        try:
            # Calculate metrics
            current_price = data['Close'].iloc[-1]
            prev_close = data['Close'].iloc[-2]
            price_change_pct = ((current_price - prev_close) / prev_close) * 100

            trend, trend_pct = self.calculate_trend(data)
            support, resistance = self.calculate_support_resistance(data)
            volume_pct = self.calculate_volume_metric(data)

            # Calculate buy/stop levels
            buy_above = resistance * 1.01  # Buy 1% above resistance
            stop = support * 0.98  # Stop 2% below support

            # Score the setup
            score, status, note = self.score_setup(data, trend, trend_pct, volume_pct)

            # Volume check - must exceed minimum
            avg_volume = data['Volume'].iloc[-20:-1].mean()
            if avg_volume < VOLUME_THRESHOLD:
                print(f"❌ (vol: {avg_volume/1e6:.1f}M)")
                return None

            scorecard = Scorecard(
                ticker=ticker,
                price=round(current_price, 2),
                price_change_pct=round(price_change_pct, 2),
                trend=trend,
                status=status,
                support=round(support, 2),
                resistance=round(resistance, 2),
                buy_above=round(buy_above, 2),
                stop=round(stop, 2),
                score=score,
                volume_pct=round(volume_pct, 1),
                setup_note=note,
                scan_time=self.scan_time,
                market=self.market,
                category=self.category
            )

            print(f"✅ (score: {score}/50)")
            return scorecard

        except Exception as e:
            print(f"❌ (error: {e})")
            return None

    def scan_all(self) -> List[Scorecard]:
        """Scan all tickers and return sorted scorecards"""
        print(f"\n{'='*80}")
        print(f"{self.market} {self.category.upper()} SCAN - {self.scan_time}")
        print(f"{'='*80}\n")

        self.scorecards = []
        for ticker in self.tickers:
            card = self.scan_ticker(ticker)
            if card:
                self.scorecards.append(card)

        # Sort by score (descending)
        self.scorecards.sort(key=lambda x: x.score, reverse=True)

        return self.scorecards

# ============================================================================
# EXPORT & REPORTING
# ============================================================================

class ScanReporter:
    """Generate reports from scan results"""

    def __init__(self, scorecards: List[Scorecard], market: str, category: str):
        self.scorecards = scorecards
        self.market = market
        self.category = category

    def export_html(self, output_dir: str = 'scan_output') -> str:
        """Export scorecards as HTML (BoxRunner-compatible format)"""
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        filename = f"{output_dir}/scan_{self.market}_{self.category}_{timestamp}.html"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{self.market} {self.category.upper()} Scan</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; background: #f5f5f5; }}
        .header {{ background: #1a1a1a; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .scancard {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin-bottom: 15px; }}
        .score-bar {{ background: #e0e0e0; height: 8px; border-radius: 4px; margin: 10px 0; overflow: hidden; }}
        .score-fill {{ height: 100%; background: #10b981; width: var(--pct); }}
        .price {{ font-size: 24px; font-weight: bold; }}
        .change {{ color: #10b981; font-size: 18px; }}
        .status {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; margin: 10px 0; }}
        .status.bullish {{ background: #d1fae5; color: #065f46; }}
        .status.bearish {{ background: #fee2e2; color: #7f1d1d; }}
        .metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 14px; margin-top: 10px; }}
        .metric {{ padding: 8px; background: #f9f9f9; border-radius: 4px; }}
        .metric-label {{ color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{self.market} {self.category.upper()} - BoxRunner Scan</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
"""

        for card in self.scorecards:
            score_pct = (card.score / SCORE_MAX) * 100
            status_class = 'bullish' if card.trend == 'Up' else 'bearish'
            change_color = '#10b981' if card.price_change_pct >= 0 else '#ef4444'

            html += f"""
    <div class="scancard">
        <div>
            <strong>{card.ticker}</strong> <span class="price">${{card.price}}</span>
            <span class="change" style="color: {change_color};">{card.price_change_pct:+.2f}%</span>
        </div>
        <div class="status {status_class}">{card.status}</div>
        <div class="score-bar">
            <div class="score-fill" style="--pct: {score_pct}%;"></div>
        </div>
        <div style="font-size: 12px; color: #666; margin: 5px 0;">{card.score}/50 — {card.setup_note}</div>
        <div class="metrics">
            <div class="metric">
                <div class="metric-label">Trend</div>
                <div>{card.trend} ({card.price_change_pct:+.1f}%)</div>
            </div>
            <div class="metric">
                <div class="metric-label">Volume</div>
                <div>{card.volume_pct:.0f}% of avg</div>
            </div>
            <div class="metric">
                <div class="metric-label">Support / Resistance</div>
                <div>${{card.support}} / ${{{card.resistance}}}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Buy Above / Stop</div>
                <div>${{{card.buy_above}}} / ${{{card.stop}}}</div>
            </div>
        </div>
    </div>
"""

        html += """
</body>
</html>
"""

        with open(filename, 'w') as f:
            f.write(html)

        return filename

    def export_json(self, output_dir: str = 'scan_output') -> str:
        """Export scorecards as JSON"""
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        filename = f"{output_dir}/scan_{self.market}_{self.category}_{timestamp}.json"

        data = [card.to_dict() for card in self.scorecards]

        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

        return filename

    def print_summary(self):
        """Print text summary to console"""
        print(f"\n{'='*80}")
        print(f"SCAN RESULTS: {self.market} {self.category.upper()}")
        print(f"{'='*80}\n")

        if not self.scorecards:
            print("No scorecards generated (check volume thresholds)\n")
            return

        for card in self.scorecards[:10]:  # Show top 10
            print(f"#{card.score}/50 | {card.ticker:6} | ${card.price:8.2f} | "
                  f"{card.trend:7} | {card.status:15} | Vol: {card.volume_pct:6.0f}%")

        print(f"\nGenerated {len(self.scorecards)} scorecards\n")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def run_scan(market: str, category: str) -> Tuple[List[Scorecard], str]:
    """
    Run scanner for market and category.
    Returns: (scorecards, html_file_path)
    """
    scanner = MarketScanner(market, category)
    scorecards = scanner.scan_all()

    reporter = ScanReporter(scorecards, market, category)
    reporter.print_summary()

    html_file = reporter.export_html()
    json_file = reporter.export_json()

    print(f"✅ HTML report: {html_file}")
    print(f"✅ JSON export: {json_file}")

    return scorecards, html_file

if __name__ == "__main__":
    # Run both markets, both categories
    print("\n🌍 STARTING DUAL-MARKET SCAN\n")

    all_scorecards = {}

    for market in ['ASX', 'US']:
        for category in ['megacap', 'midcap']:
            scorecards, html_file = run_scan(market, category)
            all_scorecards[f"{market}_{category}"] = (scorecards, html_file)

    print("\n✅ Scan complete!")
    print(f"Generated {sum(len(cards[0]) for cards in all_scorecards.values())} total scorecards")
