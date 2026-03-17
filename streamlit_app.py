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
    
    # Convert to string and remove currency symbols and commas
    str_value = str(value).replace('$', '').replace(',', '').replace('--', '0')
    
    try:
        return float(str_value)
    except (ValueError, TypeError):
        return 0.0

def clean_percentage_value(value):
    """Convert percentage string to decimal float."""
    if pd.isna(value) or value == '':
        return 0.0
    
    # Convert to string and remove percentage symbol
    str_value = str(value).replace('%', '').replace('--', '0')
    
    try:
        # Convert percentage to decimal (e.g., 2.5% -> 0.025)
        return float(str_value) / 100.0
    except (ValueError, TypeError):
        return 0.0

def calculate_cpc_recommendation(row):
    """Calculate CPC recommendation based on performance metrics."""
    impressions = int(row.get('Impressions', 0))
    clicks = int(row.get('Clicks', 0))
    conversions = float(row.get('Conversions', 0))
    cost = clean_currency_value(row.get('Cost', 0))
    current_cpc = clean_currency_value(row.get('Avg. CPC', 0))
    ctr = clean_percentage_value(row.get('CTR', 0))
    
    # Calculate cost per conversion if we have conversions
    cost_per_conversion = cost / conversions if conversions > 0 else float('inf')
    
    # Default: keep current CPC
    recommended_cpc = current_cpc
    reasoning = "Keep current bid - insufficient data or neutral performance"
    
    # Rule 1: Good performance - increase bid
    if conversions >= MIN_CONVERSIONS_FOR_CPA and cost_per_conversion <= TARGET_CPA:
        recommended_cpc = current_cpc * (1 + BID_INCREASE_PERCENT)
        reasoning = f"Increase bid by {BID_INCREASE_PERCENT*100}% - good CPA (${cost_per_conversion:.2f} ≤ ${TARGET_CPA})"
    
    # Rule 2: High CPA - decrease bid
    elif conversions >= MIN_CONVERSIONS_FOR_CPA and cost_per_conversion > TARGET_CPA:
        recommended_cpc = current_cpc * (1 - BID_DECREASE_PERCENT)
        reasoning = f"Decrease bid by {BID_DECREASE_PERCENT*100}% - high CPA (${cost_per_conversion:.2f} > ${TARGET_CPA})"
    
    # Rule 3: No conversions but high impressions and low CTR - decrease bid
    elif conversions == 0 and impressions > IMPRESSIONS_THRESHOLD_HIGH and ctr < CTR_THRESHOLD_LOW:
        recommended_cpc = current_cpc * (1 - BID_DECREASE_NO_CONV_PERCENT)
        reasoning = f"Decrease bid by {BID_DECREASE_NO_CONV_PERCENT*100}% - no conversions, high impressions ({impressions}), low CTR ({ctr*100:.2f}%)"
    
    return {
        'recommended_cpc': round(recommended_cpc, 2),
        'reasoning': reasoning,
        'cost_per_conversion': cost_per_conversion if conversions > 0 else None
    }

def identify_negative_candidates(row):
    """Identify keywords that should be considered for negative keyword lists."""
    impressions = int(row.get('Impressions', 0))
    conversions = float(row.get('Conversions', 0))
    cost = clean_currency_value(row.get('Cost', 0))
    ctr = clean_percentage_value(row.get('CTR', 0))
    
    is_negative = False
    reasoning = "Not a negative keyword candidate"
    
    # Rule 1: No conversions and high spend
    if conversions == 0 and cost > SPEND_THRESHOLD_NEGATIVE:
        is_negative = True
        reasoning = f"High spend (${cost:.2f}) with no conversions"
    
    # Rule 2: No conversions, high impressions, and very low CTR
    elif conversions == 0 and impressions > IMPRESSIONS_THRESHOLD_NEGATIVE and ctr < CTR_THRESHOLD_NEGATIVE:
        is_negative = True
        reasoning = f"High impressions ({impressions}), very low CTR ({ctr*100:.3f}%), no conversions"
    
    return {
        'is_negative_candidate': is_negative,
        'reasoning': reasoning
    }

def analyze_keywords(df):
    """Perform complete analysis on keyword data."""
    # Create a copy to avoid modifying original data
    analysis_df = df.copy()
    
    # Apply CPC recommendations
    cpc_results = analysis_df.apply(calculate_cpc_recommendation, axis=1)
    analysis_df['Recommended CPC'] = [result['recommended_cpc'] for result in cpc_results]
    analysis_df['CPC Reasoning'] = [result['reasoning'] for result in cpc_results]
    analysis_df['Cost per Conversion'] = [result['cost_per_conversion'] for result in cpc_results]
    
    # Apply negative keyword identification
    negative_results = analysis_df.apply(identify_negative_candidates, axis=1)
    analysis_df['Negative Candidate'] = [result['is_negative_candidate'] for result in negative_results]
    analysis_df['Negative Reasoning'] = [result['reasoning'] for result in negative_results]
    
    # Calculate bid change percentage and amount
    current_cpc = analysis_df['Avg. CPC'].apply(clean_currency_value)
    recommended_cpc = analysis_df['Recommended CPC']
    
    analysis_df['Bid Change %'] = ((recommended_cpc - current_cpc) / current_cpc * 100).round(1)
    analysis_df['Bid Change $'] = (recommended_cpc - current_cpc).round(2)
    
    return analysis_df

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
        
        # Allow users to adjust key parameters
        target_cpa = st.number_input("Target CPA ($)", value=TARGET_CPA, min_value=1.0, step=1.0)
        bid_increase = st.slider("Bid Increase %", min_value=5, max_value=30, value=int(BID_INCREASE_PERCENT*100))
        bid_decrease = st.slider("Bid Decrease %", min_value=5, max_value=30, value=int(BID_DECREASE_PERCENT*100))
        spend_threshold = st.number_input("Negative Keyword Spend Threshold ($)", value=SPEND_THRESHOLD_NEGATIVE, min_value=1.0, step=1.0)
        
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
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload your Google Ads CSV report",
        type=['csv'],
        help="Export your keyword performance report from Google Ads as CSV"
    )
    
    if uploaded_file is not None:
        try:
            # Read the uploaded file
            df = pd.read_csv(uploaded_file)
            
            # Validate required columns
            required_columns = ['Keyword', 'Impressions', 'Clicks', 'CTR', 'Avg. CPC', 'Cost', 'Conversions']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"Missing required columns: {', '.join(missing_columns)}")
                st.info("Please ensure your CSV export includes all required columns.")
                return
            
            # Update global variables with user inputs
            global TARGET_CPA, BID_INCREASE_PERCENT, BID_DECREASE_PERCENT, SPEND_THRESHOLD_NEGATIVE
            TARGET_CPA = target_cpa
            BID_INCREASE_PERCENT = bid_increase / 100
            BID_DECREASE_PERCENT = bid_decrease / 100
            SPEND_THRESHOLD_NEGATIVE = spend_threshold
            
            # Perform analysis
            with st.spinner("Analyzing keywords..."):
                analysis_df = analyze_keywords(df)
            
            # Display summary metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("Total Keywords", len(analysis_df))
            
            with col2:
                increase_count = (analysis_df['Bid Change %'] > 0).sum()
                st.metric("Increase Bids", increase_count, delta=f"{increase_count/len(analysis_df)*100:.1f}%")
            
            with col3:
                decrease_count = (analysis_df['Bid Change %'] < 0).sum()
                st.metric("Decrease Bids", decrease_count, delta=f"{decrease_count/len(analysis_df)*100:.1f}%")
            
            with col4:
                no_change_count = (analysis_df['Bid Change %'] == 0).sum()
                st.metric("No Change", no_change_count)
            
            with col5:
                negative_count = analysis_df['Negative Candidate'].sum()
                st.metric("Negative Candidates", negative_count, delta="Review needed" if negative_count > 0 else "None")
            
            # Display results
            st.subheader("📋 Analysis Results")
            
            # Create tabs for different views
            tab1, tab2, tab3 = st.tabs(["📊 All Keywords", "⚠️ Negative Candidates", "📈 Bid Changes"])
            
            with tab1:
                # Display full results with styling
                def style_dataframe(df):
                    def highlight_rows(row):
                        if row['Negative Candidate']:
                            return ['background-color: #ffebee'] * len(row)
                        elif row['Bid Change %'] > 0:
                            return ['background-color: #e8f5e8'] * len(row)
                        elif row['Bid Change %'] < 0:
                            return ['background-color: #fff3e0'] * len(row)
                        else:
                            return [''] * len(row)
                    
                    return df.style.apply(highlight_rows, axis=1)
                
                st.dataframe(
                    style_dataframe(analysis_df),
                    use_container_width=True,
                    height=600
                )
            
            with tab2:
                negative_df = analysis_df[analysis_df['Negative Candidate'] == True]
                if len(negative_df) > 0:
                    st.write(f"Found {len(negative_df)} negative keyword candidates:")
                    st.dataframe(negative_df[['Keyword', 'Cost', 'Impressions', 'CTR', 'Conversions', 'Negative Reasoning']], 
                               use_container_width=True)
                else:
                    st.success("No negative keyword candidates found!")
            
            with tab3:
                changes_df = analysis_df[analysis_df['Bid Change %'] != 0]
                if len(changes_df) > 0:
                    st.write(f"Recommended bid changes for {len(changes_df)} keywords:")
                    st.dataframe(changes_df[['Keyword', 'Avg. CPC', 'Recommended CPC', 'Bid Change %', 'Bid Change $', 'CPC Reasoning']], 
                               use_container_width=True)
                else:
                    st.info("No bid changes recommended with current settings.")
            
            # Download button
            st.subheader("📥 Download Results")
            
            # Prepare export data
            export_columns = [
                'Keyword', 'Impressions', 'Clicks', 'CTR', 'Avg. CPC', 'Cost', 
                'Conversions', 'Recommended CPC', 'Bid Change %', 'Bid Change $',
                'Negative Candidate', 'CPC Reasoning', 'Negative Reasoning'
            ]
            
            export_df = analysis_df[export_columns].copy()
            
            # Convert to CSV
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