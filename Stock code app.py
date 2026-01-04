import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import sys
import os
from datetime import datetime

# ================================
# 1. APP CONFIGURATION
# ================================
st.set_page_config(page_title="Pro Market Scanner", layout="wide")
st.title("NSE/BSE Market Screener")
st.markdown("Exact data view with History, MA, RSI, and News Links.")

# ================================
# 2. SIDEBAR SETTINGS
# ================================
with st.sidebar:
    st.header("Settings")
    move_pct = st.number_input("Trigger % (e.g., 5 for +/- 5%)", value=5.0, step=0.5)
    ma_window = st.number_input("MA Period", value=20, step=1)
    
    st.markdown("---")
    if st.button("START SCAN", type="primary"):
        run_scan = True
    else:
        run_scan = False

# ================================
# 3. FUNCTIONS
# ================================
@st.cache_data(ttl=3600)
def get_stock_list():
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    try:
        # NSE requires User-Agent
        df = pd.read_csv(url, storage_options={'User-Agent': 'Mozilla/5.0'})
        df.columns = df.columns.str.strip()
        base = df['SYMBOL'].unique().tolist()
        return [s + ".NS" for s in base] + [s + ".BO" for s in base]
    except Exception:
        return []

def download_data(tickers):
    # Suppress yfinance print noise
    class SuppressPrints:
        def __enter__(self):
            self._original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stderr.close()
            sys.stderr = self._original_stderr

    all_dfs = []
    chunk_size = 300
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        try:
            with SuppressPrints():
                # auto_adjust=False for EXACT Close prices
                batch = yf.download(chunk, period="3mo", interval="1d", group_by='ticker', auto_adjust=False, threads=True, progress=False)
            if not batch.empty:
                all_dfs.append(batch)
            
            # Update Progress
            progress = min((i + chunk_size) / len(tickers), 1.0)
            progress_bar.progress(progress)
            status_text.text(f"Scanning batch {i//chunk_size + 1}...")
        except: continue
            
    progress_bar.empty()
    status_text.empty()
    
    if all_dfs: return pd.concat(all_dfs, axis=1)
    return None

# ================================
# 4. MAIN LOGIC
# ================================
if run_scan:
    tickers = get_stock_list()
    st.success(f"Scanning {len(tickers)} stocks...")
    
    data = download_data(tickers)
    
    if data is not None:
        gainers = []
        losers = []
        seen = set()
        
        for ticker in tickers:
            try:
                # Handle MultiIndex
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
                above_ma_check = "Yes" if today['Close'] > today['MA'] else "No"
                
                # News Link
                news_link = f"https://www.google.com/search?q={name}+share+news&tbm=nws"

                # --- DATA ROW ---
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
                
                if is_gainer:
                    gainers.append(row)
                elif is_loser:
                    losers.append(row)
                    
            except: continue
        
        # ================================
        # 5. DISPLAY & EXPORT RESULTS
        # ================================
        st.success("Scan Complete!")
        
        tab1, tab2 = st.tabs([f"Gainers ({len(gainers)})", f"Losers ({len(losers)})"])
        
        # Helper to display dataframe nicely
        def display_tab(data_list, sort_asc):
            if data_list:
                df_res = pd.DataFrame(data_list)
                df_res = df_res.sort_values(by="Today %", ascending=sort_asc)
                
                st.dataframe(
                    df_res, 
                    use_container_width=True, 
                    height=500,
                    column_config={
                        "News Link": st.column_config.LinkColumn("News"), # Clickable Link
                        "Price": st.column_config.NumberColumn(format="₹%.2f"),
                        "Today %": st.column_config.NumberColumn(format="%.2f%%")
                    }
                )
                return df_res
            else:
                st.info("No stocks found.")
                return pd.DataFrame()

        with tab1:
            df_gainers = display_tab(gainers, False) # Descending for Gainers
            
        with tab2:
            df_losers = display_tab(losers, True)  # Ascending for Losers
            
        # --- EXCEL EXPORT (Single File, Two Sheets) ---
        if not df_gainers.empty or not df_losers.empty:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                if not df_gainers.empty:
                    df_gainers.to_excel(writer, sheet_name='Gainers', index=False)
                if not df_losers.empty:
                    df_losers.to_excel(writer, sheet_name='Losers', index=False)
            
            # Prepare file for download
            current_date_str = datetime.now().strftime("%b %d")
            file_name = f"{current_date_str} PD's Data.xlsx"
            
            st.download_button(
                label=f"📥 Download Excel Report",
                data=buffer.getvalue(),
                file_name=file_name,
                mime="application/vnd.ms-excel"
            )