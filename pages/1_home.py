# Page 1: the app's landing page (default view), with a welcome message and
# a summary of what each other page contains.
import streamlit as st

st.title("Norwegian Hydropower Reservoir Data")

st.markdown(
    """
### Welcome!

This app gives a brief overview over the Norwegian Water Resources and Energy Directorate's hydropower  
reservoir historical data (NVEs magasinstatistikk). Check out [NVE's reservoir statistics](https://www.nve.no/energi/analyser-og-statistikk/om-magasinstatistikken/) for more details.  
The data is filtered to a national level.

To navigate between the pages of the app you can use the collapsibale sidebar to the left.  


##### Content of pages
- **Table:** A table where the first column contains the column names of the imported data  
 and the second column displays the first month of the data series. The page also have a  
 dropdown-table showing a preview of the raw data.
- **Plot:** An interactive plot of the reservoir data over time, with a column selector and a  
month-range slider
- **Contact:** Page with link to my personal website with contact information.
"""
)
