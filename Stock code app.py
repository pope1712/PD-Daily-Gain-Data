import pandas as pd
import yfinance as yf
import requests
import io
import sys
import os
from datetime import datetime

# ================================
# 1. CONFIGURATION
# ================================
MOVE_PCT = 5.0      # Trigger %
MA_WINDOW = 20      # Moving Average Period
CHUNK_SIZE = 300    # Download in batches

# ================================
# 2. SOURCE: NSE (EQUITY_L.csv)
# ================================
def get_stock_list():
    print("⏳ Fetching Stock List from NSE (EQUITY_L.csv)...")
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        s = requests.get(url, headers=headers).content
        df = pd.read_csv(io.StringIO(s.decode('utf-8')))
        df.columns = df.columns.str.strip()
        base = df['SYMBOL'].unique().tolist()
        
        # Create NSE + BSE Tickers
        tickers = [s + ".NS" for s in base] + [s + ".BO" for s in base]
        
        print(f"   ✅ Found {len(base)} Base Symbols.")
        print(f"   🚀 Total Tickers to Scan: {len(tickers)}")
        return tickers
    except Exception as e:
        print(f"   ❌ Error fetching NSE list: {e}")
        return []

# ================================
# 3. SCANNER ENGINE
# ================================
def run_scan():
    tickers = get_stock_list()
    if not tickers: return

    print("\n⏳ Downloading Market Data (History, MA, RSI)...")
    
    class SuppressPrints:
        def __enter__(self):
            self._original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stderr.close()
            sys.stderr = self._original_stderr

    all_dfs = []
    
    for i in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[i:i+CHUNK_SIZE]
        print(f"   Processing Batch {i//CHUNK_SIZE + 1} / {len(tickers)//CHUNK_SIZE + 1}...", end='\r')
        
        try:
            with SuppressPrints():
                # auto_adjust=False ensures EXACT Close price
                batch = yf.download(chunk, period="3mo", interval="1d", group_by='ticker', auto_adjust=False, threads=True, progress=False)
            if not batch.empty:
                all_dfs.append(batch)
        except: continue

    print("\n✅ Download Complete. Calculating Metrics...")
    
    if not all_dfs: 
        print("❌ No data downloaded.")
        return
        
    data = pd.concat(all_dfs, axis=1)
    
    gainers = []
    losers = []
    seen = set()

    for ticker in tickers:
        try:
            # Handle MultiIndex
            if isinstance(data.columns, pd.MultiIndex):
                if ticker not in data.columns.levels[0]: continue
                df = data[ticker].copy()
            else: continue

            df.dropna(subset=['Close'], inplace=True)
            if len(df) < 25: continue 

            # --- CALCULATIONS ---
            df['Return'] = df['Close'].pct_change() * 100
            df['MA'] = df['Close'].rolling(window=MA_WINDOW).mean()

            # RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            today = df.iloc[-1]
            prev1 = df.iloc[-2]
            prev2 = df.iloc[-3]
            
            # --- FILTER ---
            is_gainer = today['Return'] >= MOVE_PCT
            is_loser = today['Return'] <= -MOVE_PCT
            
            if not (is_gainer or is_loser): continue

            # Deduplicate
            name = ticker.replace(".NS", "").replace(".BO", "")
            if name in seen: continue
            seen.add(name)

            # Volume
            avg_vol = df['Volume'].iloc[-4:-1].mean()
            vol_txt = "Above Avg" if (avg_vol > 0 and today['Volume'] > avg_vol) else "Normal"
            
            high_52 = df['Close'].max()
            dist_52 = ((today['Close'] - high_52) / high_52) * 100
            above_ma_check = "Yes" if today['Close'] > today['MA'] else "No"
            
            # News Link
            news_link = f"https://www.google.com/search?q={name}+share+news&tbm=nws"
            
            row = {
                "Symbol": name,
                "Price": round(today['Close'], 2),
                "Today %": round(today['Return'], 2),
                "Prev Day %": round(prev1['Return'], 2),
                "Prev-2 Day %": round(prev2['Return'], 2),
                "MA": round(today['MA'], 2),
                "Above MA": above_ma_check,
                "RSI": round(today['RSI'], 2),
                "Dist 52W High": f"{round(dist_52, 1)}%",
                "Volume": int(today['Volume']),
                "Volume Signal": vol_txt,
                "News Link": news_link,
                "Exchange": "NSE" if ".NS" in ticker else "BSE"
            }

            if is_gainer: gainers.append(row)
            elif is_loser: losers.append(row)

        except: continue

    # ================================
    # SAVE OUTPUT (SINGLE FILE, TWO TABS)
    # ================================
    print("\n" + "="*40)
    print(f"📊 REPORT GENERATED")
    print(f"🟢 Gainers found: {len(gainers)}")
    print(f"🔴 Losers found: {len(losers)}")
    print("="*40)

    current_date_str = datetime.now().strftime("%b %d")
    final_filename = f"{current_date_str} PD's Data.xlsx"
    
    # We use ExcelWriter to put multiple sheets in one file
    if gainers or losers:
        with pd.ExcelWriter(final_filename, engine='xlsxwriter') as writer:
            
            if gainers:
                df_gain = pd.DataFrame(gainers).sort_values(by="Today %", ascending=False)
                df_gain.to_excel(writer, sheet_name='Gainers', index=False)
                print("   Top 3 Gainers:")
                display(df_gain[['Symbol', 'Price', 'Today %', 'News Link']].head(3))
            
            if losers:
                df_loss = pd.DataFrame(losers).sort_values(by="Today %", ascending=True)
                df_loss.to_excel(writer, sheet_name='Losers', index=False)
                
        print(f"\n✅ Successfully Saved: {final_filename}")
        print("   (Open the file and check the bottom tabs for Gainers/Losers)")
    else:
        print("ℹ️ No stocks found matching criteria.")

if __name__ == "__main__":
    run_scan()