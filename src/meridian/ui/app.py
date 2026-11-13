"""Operator screen: task, plan, live step log, OTP box, disputes awaiting approval, results."""
import streamlit as st

st.set_page_config(page_title="Meridian Portal Agent", layout="wide")
st.title("Meridian Portal Agent")
st.caption("TransIndus invoice reconciliation · Team Delta · synthetic data only")

task_text = st.text_input("Task", placeholder="Reconcile all invoices on lane PUN-HYD dated in October 2026")
left, right = st.columns(2)
with left:
    st.subheader("Live step log")
    st.info("Not wired up yet.")
with right:
    st.subheader("One-time password")
    st.text_input("OTP from operator inbox", type="password", disabled=True)
    st.subheader("Disputes awaiting approval")
    st.info("None.")
st.subheader("Results")
st.info("No runs yet.")
