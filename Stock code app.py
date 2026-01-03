import streamlit as st
import pandas as pd
import yfinance as yf
import sys
import os

# ================================
# 1️⃣ APP CONFIGURATION
# ================================
st.set_page_config(page_title="Pro Market Scanner", page_icon="📊", layout="wide")
st.title("🚀 NSE/BSE Market Screener")
st.markdown("Exact data view with **History**, **MA**, and **RSI**.")

# ================================
# 2️⃣ SIDEBAR SETTINGS
# ================================
with st.sidebar:
    st.header("⚙️ Settings")
    move_pct = st.number_input("Trigger % (e.g., 5 for +/- 5%)", value=5.0, step=0.5)
    ma_window = st.number_input("MA Period", value=20, step=1)
    
    st.markdown("---")
    if st.button("🔎 START SCAN", type="primary"):
        run_scan = True
    else:
        run_scan = False

# ================================
# 3️⃣ FUNCTIONS
# ================================
@st.cache_data(ttl=3600)
def get_stock_list():
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    try:
        df = pd.read_csv(url, storage_options={'User-Agent': 'Mozilla/5.0'})
        df.columns = df.columns.str.strip()
        base = df['SYMBOL'].unique().tolist()
        return [s + ".NS" for s in base] + [s + ".BO" for s in base]
    except Exception:
        return []

def download_data(tickers):
    class SuppressPrints:
        def __enter__(self):
            self._original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stderr.close()
            sys.stderr = self._original_stderr

    all_dfs = []
    chunk_size = 300
    
    progress = st.progress(0)
    status = st.empty()
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            with SuppressPrints():
                batch = yf.download(chunk, period="1y", interval="1d", group_by='ticker', auto_adjust=True, threads=True, progress=False)
            if not batch.empty:
                all_dfs.append(batch)
            progress.progress(min((i + chunk_size) / len(tickers), 1.0))
            status.caption(f"Scanning batch {i//chunk_size + 1}...")
        except: continue
            
    progress.empty()
    status.empty()
    
    if all_dfs: return pd.concat(all_dfs, axis=1)
    return None

# ================================
# 4️⃣ MAIN LOGIC
# ================================
if run_scan:
    tickers = get_stock_list()
    st.toast(f"Scanning {len(tickers)} stocks...")
    
    data = download_data(tickers)
    
    if data is not None:
        gainers = []
        losers = []
        seen = set()
        
        for ticker in tickers:
            try:
                if ticker not in data.columns.levels[0]: continue
                
                df = data[ticker].copy()
                df.dropna(subset=['Close'], inplace=True)
                if len(df) < 25: continue
                
                # --- CALCULATIONS ---
                df['Return'] = df['Close'].pct_change() * 100
                df['MA'] = df['Close'].rolling(window=ma_window).mean()
                
                # RSI Calculation
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                df['RSI'] = 100 - (100 / (1 + rs))

                today = df.iloc[-1]
                prev1 = df.iloc[-2]
                prev2 = df.iloc[-3]
                
                # Filter: Gainer OR Loser
                is_gainer = today['Return'] >= move_pct
                is_loser = today['Return'] <= -move_pct
                
                if not (is_gainer or is_loser): continue

                # Deduplicate
                name = ticker.replace(".NS", "").replace(".BO", "")
                if name in seen: continue
                seen.add(name)
                
                # Volume Logic
                avg_vol = df['Volume'].iloc[-4:-1].mean()
                vol_txt = "Above Avg" if (avg_vol > 0 and today['Volume'] > avg_vol) else "Normal"
                
                # 52W High Distance
                high_52 = df['Close'].max()
                dist_52 = ((today['Close'] - high_52) / high_52) * 100
                
                # Above MA Check
                above_ma_check = "✅" if today['Close'] > today['MA'] else "❌"

                # --- DATA ROW (Exact Match to Your Request) ---
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
                    "Exchange": "NSE" if ".NS" in ticker else "BSE"
                }
                
                if is_gainer:
                    gainers.append(row)
                elif is_loser:
                    losers.append(row)
                    
            except: continue
        
        # ================================
        # 5️⃣ DISPLAY RESULTS
        # ================================
        st.success("Scan Complete!")
        
        tab1, tab2 = st.tabs([f"🟢 Gainers ({len(gainers)})", f"🔴 Losers ({len(losers)})"])
        
        def show_tab(data_list, filename):
            if data_list:
                df_res = pd.DataFrame(data_list)
                
                # Sort Logic
                sort_asc = True if "loser" in filename else False
                df_res = df_res.sort_values(by="Today %", ascending=sort_asc)
                
                # Format Columns specifically for Streamlit Table
                column_config = {
                    "Price": st.column_config.NumberColumn(format="₹%.2f"),
                    "Today %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Prev Day %": st.column_config.NumberColumn(format="%.2f%%"),
                    "Prev-2 Day %": st.column_config.NumberColumn(format="%.2f%%"),
                    "MA": st.column_config.NumberColumn(format="%.2f"),
                    "RSI": st.column_config.NumberColumn(format="%.1f"),
                }
                
                st.dataframe(
                    df_res, 
                    use_container_width=True, 
                    height=600, 
                    column_config=column_config
                )
                
                # Download Button
                csv = df_res.to_csv(index=False).encode('utf-8')
                st.download_button(f"📥 Download CSV", csv, filename, "text/csv")
            else:
                st.info("No stocks found.")

        with tab1:
            show_tab(gainers, "gainers.csv")
            
        with tab2:
            show_tab(losers, "losers.csv")