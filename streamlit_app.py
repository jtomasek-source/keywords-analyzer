import streamlit as st
import pandas as pd
import io
from datetime import datetime

# =============================================================================
# CONFIGURATION CONSTANTS - MODIFY THESE TO ADJUST RECOMMENDATION LOGIC
# =============================================================================

# Target Cost Per Acquisition - adjust based on your business goals
TARGET_CPA = 50.0

# CTR thresholds for different scenarios
CTR_THRESHOLD_LOW = 0.01  # 1% - threshold for low CTR with high impressions
CTR_THRESHOLD_NEGATIVE = 0.005  # 0.5% - threshold for negative keyword candidates

# Spend thresholds
SPEND_THRESHOLD_NEGATIVE = 20.0  # $20 - minimum spend to consider for negative keywords
IMPRESSIONS_THRESHOLD_HIGH = 100  # High impression threshold for CPC decisions
IMPRESSIONS_THRESHOLD_NEGATIVE = 200  # Impression threshold for negative keyword candidates

# Bid adjustment percentages
BID_INCREASE_PERCENT = 0.10  # 10% increase for good performers
BID_DECREASE_PERCENT = 0.15  # 15% decrease for high CPA
BID_DECREASE_NO_CONV_PERCENT = 0.20  # 20% decrease for no conversions

# Minimum conversions to consider for CPA-based decisions
MIN_CONVERSIONS_FOR_CPA = 5

# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def clean_currency_value(value):
    """Convert currency string to float, handling various formats."""
    if pd.isna(value) or value == '':
        return 0.0
    
    str_value = str(value).replace('$', '').replace(',', '').replace('--', '0')
    
    try:
        return float(str_value)
    except (ValueError, TypeError):
        return 0.0

def clean_percentage_value(value):
    """Convert percentage string to decimal float."""
    if pd.isna(value) or value == '':
        return 0.0
    
    str_value = str(value).replace('%', '').replace('--', '0')
    
    try:
        return float(str_value) / 100.0
    except (ValueError, TypeError):
        return 0.0

# =============================================================================
# STREAMLIT APP
# =============================================================================

def main():
    st.set_page_config(
        page_title="Google Ads Keyword Analyzer",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("📊 Google Ads Keyword Analyzer")
    st.markdown("Upload your Google Ads keyword performance report and get optimization recommendations!")
    
    # Sidebar with configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        target_cpa = st.number_input("Target CPA ($)", value=50.0, min_value=1.0, step=1.0)
        bid_increase = st.slider("Bid Increase %", min_value=5, max_value=30, value=10)
        bid_decrease = st.slider("Bid Decrease %", min_value=5, max_value=30, value=15)
        spend_threshold = st.number_input("Negative Keyword Spend Threshold ($)", value=20.0, min_value=1.0, step=1.0)
        
        st.markdown("---")
        st.markdown("**Required CSV Columns:**")
        st.markdown("""
        - Keyword
        - Impressions
        - Clicks
        - CTR
        - Avg. CPC
        - Cost
        - Conversions
        """)
    
    uploaded_file = st.file_uploader(
        "Upload your Google Ads CSV report",
        type=['csv'],
        help="Export your keyword performance report from Google Ads as CSV"
    )
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            
            required_columns = ['Keyword', 'Impressions', 'Clicks', 'CTR', 'Avg. CPC', 'Cost', 'Conversions']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"Missing required columns: {', '.join(missing_columns)}")
                st.info("Please ensure your CSV export includes all required columns.")
                return
            
            with st.spinner("Analyzing keywords..."):
                analysis_df = df.copy()
                
                # Define analysis functions with user parameters
                def calc_cpc_rec(row):
                    impressions = int(row.get('Impressions', 0))
                    conversions = float(row.get('Conversions', 0))
                    cost = clean_currency_value(row.get('Cost', 0))
                    current_cpc = clean_currency_value(row.get('Avg. CPC', 0))
                    ctr = clean_percentage_value(row.get('CTR', 0))
                    
                    cost_per_conversion = cost / conversions if conversions > 0 else float('inf')
                    recommended_cpc = current_cpc
                    reasoning = "Keep current bid - insufficient data or neutral performance"
                    
                    bid_inc = bid_increase / 100
                    bid_dec = bid_decrease / 100
                    
                    if conversions >= MIN_CONVERSIONS_FOR_CPA and cost_per_conversion <= target_cpa:
                        recommended_cpc = current_cpc * (1 + bid_inc)
                        reasoning = f"Increase bid by {bid_increase}% - good CPA (${cost_per_conversion:.2f} <= ${target_cpa})"
                    elif conversions >= MIN_CONVERSIONS_FOR_CPA and cost_per_conversion > target_cpa:
                        recommended_cpc = current_cpc * (1 - bid_dec)
                        reasoning = f"Decrease bid by {bid_decrease}% - high CPA (${cost_per_conversion:.2f} > ${target_cpa})"
                    elif conversions == 0 and impressions > IMPRESSIONS_THRESHOLD_HIGH and ctr < CTR_THRESHOLD_LOW:
                        recommended_cpc = current_cpc * (1 - BID_DECREASE_NO_CONV_PERCENT)
                        reasoning = f"Decrease bid by {BID_DECREASE_NO_CONV_PERCENT*100}% - no conversions, high impressions"
                    
                    return {
                        'recommended_cpc': round(recommended_cpc, 2),
                        'reasoning': reasoning,
                        'cost_per_conversion': cost_per_conversion if conversions > 0 else None
                    }
                
                def calc_neg(row):
                    impressions = int(row.get('Impressions', 0))
                    conversions = float(row.get('Conversions', 0))
                    cost = clean_currency_value(row.get('Cost', 0))
                    ctr = clean_percentage_value(row.get('CTR', 0))
                    
                    is_negative = False
                    reasoning = "Not a negative keyword candidate"
                    
                    if conversions == 0 and cost > spend_threshold:
                        is_negative = True
                        reasoning = f"High spend (${cost:.2f}) with no conversions"
                    elif conversions == 0 and impressions > IMPRESSIONS_THRESHOLD_NEGATIVE and ctr < CTR_THRESHOLD_NEGATIVE:
                        is_negative = True
                        reasoning = f"High impressions ({impressions}), very low CTR ({ctr*100:.3f}%), no conversions"
                    
                    return {'is_negative_candidate': is_negative, 'reasoning': reasoning}
                
                # Apply analysis
                cpc_results = analysis_df.apply(calc_cpc_rec, axis=1)
                analysis_df['Recommended CPC'] = [r['recommended_cpc'] for r in cpc_results]
                analysis_df['CPC Reasoning'] = [r['reasoning'] for r in cpc_results]
                analysis_df['Cost per Conversion'] = [r['cost_per_conversion'] for r in cpc_results]
                
                neg_results = analysis_df.apply(calc_neg, axis=1)
                analysis_df['Negative Candidate'] = [r['is_negative_candidate'] for r in neg_results]
                analysis_df['Negative Reasoning'] = [r['reasoning'] for r in neg_results]
                
                current_cpc_vals = analysis_df['Avg. CPC'].apply(clean_currency_value)
                recommended_cpc_vals = analysis_df['Recommended CPC']
                
                analysis_df['Bid Change %'] = ((recommended_cpc_vals - current_cpc_vals) / current_cpc_vals * 100).round(1)
                analysis_df['Bid Change $'] = (recommended_cpc_vals - current_cpc_vals).round(2)
            
            # Summary stats
            total_keywords = len(analysis_df)
            negative_candidates = analysis_df['Negative Candidate'].sum()
            increase_bids = (analysis_df['Bid Change %'] > 0).sum()
            decrease_bids = (analysis_df['Bid Change %'] < 0).sum()
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("Total Keywords", total_keywords)
            with col2:
                st.metric("Increase Bids", increase_bids, delta=f"{increase_bids/total_keywords*100:.1f}%")
            with col3:
                st.metric("Decrease Bids", decrease_bids, delta=f"{decrease_bids/total_keywords*100:.1f}%")
            with col4:
                no_change = total_keywords - increase_bids - decrease_bids
                st.metric("No Change", no_change)
            with col5:
                st.metric("Negative Candidates", negative_candidates, delta="Review" if negative_candidates > 0 else "None")
            
            st.subheader("📋 Analysis Results")
            
            tab1, tab2, tab3 = st.tabs(["📊 All Keywords", "⚠️ Negative Candidates", "📈 Bid Changes"])
            
            with tab1:
                def highlight_rows(row):
                    if row['Negative Candidate']:
                        return ['background-color: #ffebee'] * len(row)
                    elif row['Bid Change %'] > 0:
                        return ['background-color: #e8f5e8'] * len(row)
                    elif row['Bid Change %'] < 0:
                        return ['background-color: #fff3e0'] * len(row)
                    else:
                        return [''] * len(row)
                
                st.dataframe(
                    analysis_df.style.apply(highlight_rows, axis=1),
                    use_container_width=True,
                    height=600
                )
            
            with tab2:
                negative_df = analysis_df[analysis_df['Negative Candidate'] == True]
                if len(negative_df) > 0:
                    st.write(f"Found {len(negative_df)} negative keyword candidates:")
                    st.dataframe(
                        negative_df[['Keyword', 'Cost', 'Impressions', 'CTR', 'Conversions', 'Negative Reasoning']], 
                        use_container_width=True
                    )
                else:
                    st.success("No negative keyword candidates found!")
            
            with tab3:
                changes_df = analysis_df[analysis_df['Bid Change %'] != 0]
                if len(changes_df) > 0:
                    st.write(f"Recommended bid changes for {len(changes_df)} keywords:")
                    st.dataframe(
                        changes_df[['Keyword', 'Avg. CPC', 'Recommended CPC', 'Bid Change %', 'Bid Change $', 'CPC Reasoning']], 
                        use_container_width=True
                    )
                else:
                    st.info("No bid changes recommended with current settings.")
            
            st.subheader("📥 Download Results")
            
            export_columns = [
                'Keyword', 'Impressions', 'Clicks', 'CTR', 'Avg. CPC', 'Cost', 
                'Conversions', 'Recommended CPC', 'Bid Change %', 'Bid Change $',
                'Negative Candidate', 'CPC Reasoning', 'Negative Reasoning'
            ]
            
            export_df = analysis_df[export_columns].copy()
            csv_buffer = io.StringIO()
            export_df.to_csv(csv_buffer, index=False)
            csv_data = csv_buffer.getvalue()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"keyword_analysis_{timestamp}.csv"
            
            st.download_button(
                label="📁 Download Analysis Results (CSV)",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                help="Download the complete analysis results as a CSV file"
            )
            
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
            st.info("Please ensure your file is a valid CSV with the required columns.")

if __name__ == "__main__":
    main()
