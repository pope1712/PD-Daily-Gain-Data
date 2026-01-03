import streamlit as st
import pandas as pd
import yfinance as yf
import sys
import os

# ================================
# 1️⃣ APP CONFIGURATION (Mobile Friendly)
# ================================
st.set_page_config(
    page_title="Stock Screener", 
    page_icon="📈", 
    layout="wide"
)

st.title("📱 Free Mobile Stock Screener")
st.markdown("Scans NSE & BSE for **>5% Gains** and **High Volume**.")
st.info("ℹ️ Since this runs on the Cloud, use the **Download** button to save results to your phone/laptop.")

# ================================
# 2️⃣ SIDEBAR SETTINGS
# ================================
with st.sidebar:
    st.header("⚙️ Settings")
    min_gain = st.number_input("Min Gain %", value=5.0, step=0.5)
    ma_window = st.number_input("MA Period", value=20, step=1)
    
    st.markdown("---")
    if st.button("🔎 START SCAN", type="primary"):
        run_scan = True
    else:
        run_scan = False

# ================================
# 3️⃣ CORE FUNCTIONS
# ================================
@st.cache_data(ttl=3600)
def get_stock_list():
    """Fetches tickers from NSE."""
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    try:
        df = pd.read_csv(url, storage_options={'User-Agent': 'Mozilla/5.0'})
        df.columns = df.columns.str.strip()
        base = df['SYMBOL'].unique().tolist()
        
        # Create Ticker List (NSE Priority)
        nse = [s + ".NS" for s in base]
        bse = [s + ".BO" for s in base]
        return nse + bse
    except Exception as e:
        st.error(f"Error fetching list: {e}")
        return []

def download_data(tickers):
    """Downloads market data."""
    # Helper to silence error messages
    class SuppressPrints:
        def __enter__(self):
            self._original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stderr.close()
            sys.stderr = self._original_stderr

    all_dfs = []
    chunk_size = 300
    
    # Progress Bar
    progress = st.progress(0)
    status = st.empty()
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            with SuppressPrints():
                # Download 1 Year of data
                batch = yf.download(chunk, period="1y", interval="1d", group_by='ticker', auto_adjust=True, threads=True, progress=False)
            if not batch.empty:
                all_dfs.append(batch)
            
            # Update Progress
            prog = min((i + chunk_size) / len(tickers), 1.0)
            progress.progress(prog)
            status.caption(f"Scanning batch {i//chunk_size + 1}...")
        except:
            continue
            
    progress.empty()
    status.empty()
    
    if all_dfs:
        return pd.concat(all_dfs, axis=1)
    return None

# ================================
# 4️⃣ MAIN LOGIC
# ================================
if run_scan:
    tickers = get_stock_list()
    st.toast(f"Loaded {len(tickers)} stocks. Starting scan...")
    
    data = download_data(tickers)
    
    if data is not None:
        results = []
        seen = set()
        
        for ticker in tickers:
            try:
                if ticker not in data.columns.levels[0]: continue
                
                df = data[ticker].copy()
                df.dropna(subset=['Close'], inplace=True)
                if len(df) < 25: continue 
                
                # Calculations
                df['Return'] = df['Close'].pct_change() * 100
                df['MA20'] = df['Close'].rolling(window=ma_window).mean()
                
                today = df.iloc[-1]
                
                # FILTER: Min Gain
                if today['Return'] <= min_gain: continue
                
                # DEDUPLICATE (Keep NSE)
                name = ticker.replace(".NS", "").replace(".BO", "")
                if name in seen: continue
                seen.add(name)
                
                # Metrics
                prev1 = df.iloc[-2]
                prev2 = df.iloc[-3]
                
                # Trend
                trend = "🟢 UP" if (prev1['Return'] > 0 and prev2['Return'] > 0) else "Mixed"
                
                # Volume
                avg_vol = df['Volume'].iloc[-4:-1].mean()
                vol_signal = "🔥 High" if (avg_vol > 0 and today['Volume'] > avg_vol) else "Normal"
                
                # 52W High
                high_52 = df['Close'].max()
                dist_52 = ((today['Close'] - high_52) / high_52) * 100
                
                exch = "NSE" if ".NS" in ticker else "BSE"

                results.append({
                    "Symbol": name,
                    "Price": round(today['Close'], 2),
                    "Change %": round(today['Return'], 2),
                    "Trend": trend,
                    "Volume": vol_signal,
                    "52W Dist": f"{round(dist_52, 1)}%",
                    "Exchange": exch
                })
            except: continue
        
        # DISPLAY
        if results:
            df_final = pd.DataFrame(results).sort_values(by="Change %", ascending=False)
            st.success(f"✅ Found {len(df_final)} Stocks!")
            
            # Interactive Table
            st.dataframe(df_final, use_container_width=True, height=500)
            
            # DOWNLOAD BUTTON (Works on Android/Cloud)
            csv = df_final.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Results (CSV)",
                data=csv,
                file_name="stock_scan.csv",
                mime="text/csv"
            )
        else:
            st.warning("No stocks found matching criteria.")