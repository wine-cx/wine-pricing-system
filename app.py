
import streamlit as st
import pandas as pd
import json
import re
from io import BytesIO
from pathlib import Path

# 页面配置
st.set_page_config(page_title="红酒报价系统", layout="wide")
st.sidebar.title("🔧 导航")
page = st.sidebar.radio("", ["清洗", "查询"])

# 本地路径
UPLOAD_DIR = Path(r"E:\wine_checker\uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_PATH = Path(r"E:\wine_checker\cleaned_data.xlsx")
SUPPLIER_INFO_PATH = Path(r"E:\wine_checker\supplier_info.json")
TEMPLATE_PATH = Path(__file__).parent / "column_memory.json"

# 加载函数
def load_json(path: Path) -> dict:
    return json.load(path.open(encoding="utf-8-sig"))

@st.cache_data
def load_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)

@st.cache_data
def load_cleaned(path: Path) -> pd.DataFrame | None:
    return pd.read_excel(path) if path.exists() else None

# 初始加载
template_dict = load_json(TEMPLATE_PATH)
supplier_info = load_json(SUPPLIER_INFO_PATH) if SUPPLIER_INFO_PATH.exists() else {}
prev = load_cleaned(CLEANED_PATH)
if prev is not None and 'df_clean' not in st.session_state:
    st.session_state['df_clean'] = prev

# 工具函数
def extract_code(fn: str) -> str | None:
    m = re.search(r"(\d{3})", fn)
    return m.group(1) if m else None

def match_template(code: str):
    for key, tpl in template_dict.items():
        if code and code in key:
            return key, tpl
    return None, None

def letter_to_index(s: str) -> int | None:
    s = str(s).strip().upper(); idx = 0
    for c in s:
        if not ('A' <= c <= 'Z'): return None
        idx = idx * 26 + (ord(c) - ord('A') + 1)
    return idx - 1

def get_col(df: pd.DataFrame, spec: str) -> pd.Series:
    if not spec or pd.isna(spec): return pd.Series([''] * len(df))
    s = str(spec).strip().lower()
    if ',' in s:
        parts = s.split(','); out = None
        for p in parts:
            i = letter_to_index(p.strip())
            col = df.iloc[:, i].astype(str) if i is not None and i < df.shape[1] else pd.Series(['列越界'] * len(df))
            out = col if out is None else out.str.cat(col, sep=' ')
        return out
    if '-' in s:
        a, b = s.split('-'); i1, i2 = letter_to_index(a), letter_to_index(b)
        if i1 is None or i1 >= df.shape[1]: return pd.Series(['列越界'] * len(df))
        i2 = min(i2 if i2 is not None else df.shape[1] - 1, df.shape[1] - 1)
        out = df.iloc[:, i1].astype(str)
        for j in range(i1+1, i2+1): out = out.str.cat(df.iloc[:, j].astype(str), sep=' ')
        return out
    i = letter_to_index(s)
    return df.iloc[:, i].astype(str) if i is not None and i < df.shape[1] else pd.Series(['列越界'] * len(df))

def extract_data(df: pd.DataFrame, tpl: dict, supplier: str, src: str) -> pd.DataFrame:
    return pd.DataFrame({
        '酒名英文': get_col(df, tpl.get('酒名英文','')),
        '酒名中文': get_col(df, tpl.get('酒名中文','')),
        '年份':      get_col(df, tpl.get('年份','')).str.extract(r'(19\d{2}|20\d{2})')[0],
        '单价':      get_col(df, tpl.get('单价','')),
        '支数':      get_col(df, tpl.get('支数','')),
        '酒商':      supplier
    })

def parse_supplier(fn: str) -> str:
    name = re.sub(r'\.(xlsx|csv)$','', fn, flags=re.IGNORECASE)
    return re.sub(r'\(\d{2,3}\)','', name).strip()

# 清洗页面
if page == "清洗":
    st.header("📥 数据清洗与合并")

    if st.button("字段管理"):
        st.session_state['field_mode'] = not st.session_state.get('field_mode', False)

    if st.session_state.get('field_mode', False):
        st.subheader("字段映射配置管理")
        all_keys = sorted(template_dict.keys())
        cols = sorted({k for tpl in template_dict.values() for k in tpl})
        rows = []
        for key in all_keys:
            row = {'supplier': key}
            for c in cols: row[c] = template_dict[key].get(c, '')
            rows.append(row)
        df_tpl = pd.DataFrame(rows)
        edited = st.data_editor(df_tpl, num_rows="dynamic")
    if st.button("保存字段配置"):
        new_dict = {}
        for _, r in edited.iterrows():
            sup = r['supplier']
            val = {c: r[c] for c in cols if pd.notna(r[c]) and r[c] != ''}
            new_dict[sup] = val
        with open(TEMPLATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_dict, f, ensure_ascii=False, indent=2)
        st.success("✅ 配置已保存，页面将自动刷新以应用新字段...")
        try:
            st.experimental_rerun()
        except Exception:
            st.info("⚠️ 当前环境不支持自动刷新，请手动刷新页面")

    if st.button("管理上传记录"):
        st.session_state['manage_mode'] = not st.session_state.get('manage_mode', False)

    if st.session_state.get('manage_mode', False):
        st.subheader("📂 上传记录管理")
        for path in sorted(UPLOAD_DIR.glob("*.xlsx")):
            key, tpl = match_template(extract_code(path.name))
            status = "✅ 成功" if tpl else "❌ 未匹配"
            st.markdown(f"**{path.name}** — {status}")
            if tpl and st.button(f"查看预览 {path.name}", key=f"pv_{path.name}"):
                df0 = load_excel(path)
                sup = tpl.get('酒商','') or tpl.get('display_name','') or parse_supplier(path.name)
                st.dataframe(extract_data(df0, tpl, sup, path.name).head(5), use_container_width=True)
            if st.button(f"删除 {path.name}", key=f"dl_{path.name}"):
                path.unlink(); st.experimental_rerun()
        st.markdown("---")

    uploaded = st.file_uploader("📤 上传报价文件(.xlsx 多选)", type="xlsx", accept_multiple_files=True)
    if uploaded:
        for f in uploaded:
            dest = UPLOAD_DIR / f.name
            if not dest.exists(): dest.write_bytes(f.getvalue())
        st.success("上传完成")

    if st.button("开始清洗所有文件"):
        merged = []
        for path in sorted(UPLOAD_DIR.glob("*.xlsx")):
            key, tpl = match_template(extract_code(path.name))
            if not tpl: continue
            df0 = load_excel(path)
            sup = tpl.get('酒商','') or tpl.get('display_name','') or parse_supplier(path.name)
            merged.append(extract_data(df0, tpl, sup, path.name))
        if merged:
            df_clean = pd.concat(merged, ignore_index=True)
            df_clean.to_excel(CLEANED_PATH, index=False)
            st.success("清洗完成并保存")
            st.dataframe(df_clean.head(20), use_container_width=True)
            buf = BytesIO(); df_clean.to_excel(buf, index=False)
            st.download_button("下载清洗结果", buf.getvalue(), file_name="cleaned_data.xlsx")
            st.session_state['df_clean'] = df_clean

# 查询页面
else:
    st.header("🔍 数据查询")
    df_q = None
    up = st.file_uploader("上传清洗结果(.xlsx/.csv)", type=["xlsx", "csv"])
    if up:
        df_q = pd.read_excel(up) if up.name.endswith("xlsx") else pd.read_csv(up)
        df_q.to_excel(CLEANED_PATH, index=False)
        st.session_state['df_clean'] = df_q
    elif 'df_clean' in st.session_state:
        df_q = st.session_state['df_clean']
    else:
        st.warning("请先清洗或上传文件")
        st.stop()

    cols = ["酒名英文", "酒名中文", "年份", "单价", "支数", "酒商"]
    col1, col2, col3 = st.columns(3)
    with col1: kw = st.text_input("关键词")
    with col2:
        sp = st.selectbox("供应商", ["全部"] + sorted(df_q['酒商'].dropna().unique()))
    with col3:
        yf = st.selectbox("年份", ["全部"] + sorted(df_q['年份'].dropna().astype(str).unique()))

    if st.button("查询"):
        df2 = df_q.copy()
        if kw:
            mask = (
                df2['酒名英文'].str.contains(kw, case=False, na=False) |
                df2['酒名中文'].str.contains(kw, case=False, na=False) |
                df2['年份'].astype(str).str.contains(kw, na=False)
            )
            df2 = df2[mask]
        if sp != "全部": df2 = df2[df2["酒商"] == sp]
        if yf != "全部": df2 = df2[df2["年份"] == yf]
        if df2.empty:
            st.warning("无匹配记录")
        else:
            df2['_price'] = pd.to_numeric(df2['单价'].str.replace(r'[^0-9\.]','', regex=True), errors='coerce')
            df2 = df2.sort_values('_price')
            st.dataframe(df2[cols].reset_index(drop=True), use_container_width=True, height=600)
