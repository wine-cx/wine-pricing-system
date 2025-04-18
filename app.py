import streamlit as st
import pandas as pd
import json
import re
from io import BytesIO
from pathlib import Path
import urllib.parse
import streamlit.components.v1 as components

# —— 页面配置 —— #
st.set_page_config(page_title="红酒报价系统", layout="wide")
st.sidebar.title("🔧 导航")
page = st.sidebar.radio("页面", ["清洗", "查询", "供应商管理"])

# —— 本地目录 & URL 配置 —— #
UPLOAD_DIR         = Path(r"E:\wine_checker\uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CLEANED_PATH       = Path(r"E:\wine_checker\cleaned_data.xlsx")
SUPPLIER_INFO_PATH = Path(r"E:\wine_checker\supplier_info.json")
TEMPLATE_PATH      = Path(__file__).parent / "column_memory.json"
UPLOAD_URL_BASE    = "https://your-domain.com/uploads"

# —— 加载函数 —— #
def load_json(path: Path) -> dict:
    return json.load(path.open(encoding="utf-8-sig")) if path.exists() else {}

@st.cache_data
def load_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)

@st.cache_data
def load_cleaned(path: Path):
    return pd.read_excel(path) if path.exists() else None

# —— 初始化 —— #
template_dict = load_json(TEMPLATE_PATH)
supplier_info = load_json(SUPPLIER_INFO_PATH)
prev = load_cleaned(CLEANED_PATH)
if prev is not None and "df_clean" not in st.session_state:
    st.session_state["df_clean"] = prev

# —— 通用函数 —— #
def extract_code(fn: str):
    m = re.search(r"(\d{3})", fn)
    return m.group(1) if m else None

def match_template(code: str):
    for key, tpl in template_dict.items():
        if code and code in key:
            return key, tpl
    return None, None

def letter_to_index(s: str):
    s = str(s).strip().upper()
    idx = 0
    for c in s:
        if not ("A" <= c <= "Z"):
            return None
        idx = idx * 26 + (ord(c) - ord("A") + 1)
    return idx - 1

def get_col(df: pd.DataFrame, spec: str) -> pd.Series:
    if not spec or pd.isna(spec):
        return pd.Series([""] * len(df))
    s = str(spec).strip().lower()
    if "," in s:
        out = None
        for part in s.split(","):
            i = letter_to_index(part.strip())
            col = df.iloc[:, i].astype(str) if i is not None and i < df.shape[1] else pd.Series(["列越界"]*len(df))
            out = col if out is None else out.str.cat(col, sep=" ")
        return out
    if "-" in s:
        a, b = s.split("-")
        i1, i2 = letter_to_index(a), letter_to_index(b)
        if i1 is None or i1 >= df.shape[1]:
            return pd.Series(["列越界"]*len(df))
        i2 = min(i2 if i2 is not None else df.shape[1]-1, df.shape[1]-1)
        out = df.iloc[:, i1].astype(str)
        for j in range(i1+1, i2+1):
            out = out.str.cat(df.iloc[:, j].astype(str), sep=" ")
        return out
    idx = letter_to_index(s)
    return df.iloc[:, idx].astype(str) if idx is not None and idx < df.shape[1] else pd.Series(["列越界"]*len(df))

def extract_data(df: pd.DataFrame, tpl: dict, supplier: str) -> pd.DataFrame:
    return pd.DataFrame({
        "酒名英文": get_col(df, tpl.get("酒名英文","")),
        "酒名中文": get_col(df, tpl.get("酒名中文","")),
        "年份":     get_col(df, tpl.get("年份","")).str.extract(r"(19\d{2}|20\d{2})")[0],
        "单价":     get_col(df, tpl.get("单价","")),
        "支数":     get_col(df, tpl.get("支数","")),
        "酒商":     supplier,  # 直接使用文件名
    })

# —— 清洗 页面 —— #
if page == "清洗":
    st.header("📥 数据清洗与合并")

    if st.button("字段管理"):
        st.session_state['field_mode'] = not st.session_state.get('field_mode', False)
    if st.session_state.get('field_mode', False):
        st.subheader("🛠 字段映射配置管理")
        keys = sorted(template_dict.keys())
        cols = sorted({c for tpl in template_dict.values() for c in tpl})
        rows = []
        for key in keys:
            row = {"supplier": key}
            for c in cols:
                row[c] = template_dict[key].get(c,"")
            rows.append(row)
        df_tpl = pd.DataFrame(rows)
        edited = st.data_editor(df_tpl, num_rows="dynamic")
        if st.button("保存字段配置"):
            newd = {
                r["supplier"]: {c:r[c] for c in cols if pd.notna(r[c]) and r[c]!=""}
                for _,r in edited.iterrows()
            }
            with open(TEMPLATE_PATH,"w",encoding="utf-8") as f:
                json.dump(newd,f,ensure_ascii=False,indent=2)
            st.success("✅ 字段配置已保存，刷新生效")
            st.stop()

    if st.button("管理上传记录"):
        st.session_state['manage_mode'] = not st.session_state.get('manage_mode', False)
    if st.session_state.get('manage_mode', False):
        st.subheader("📂 上传记录管理")
        for path in sorted(UPLOAD_DIR.glob("*.xlsx")):
            key, tpl = match_template(extract_code(path.name))
            status = "✅ 已匹配" if tpl else "❌ 未匹配"
            st.markdown(f"**{path.name}** — {status}")
            if tpl and st.button(f"预览 {path.name}", key=f"pv_{path.name}"):
                df0 = load_excel(path)
                st.dataframe(extract_data(df0, tpl, path.name).head(5), use_container_width=True)
            if st.button(f"删除 {path.name}", key=f"del_{path.name}"):
                path.unlink()
                st.rerun()
        st.markdown("---")

    uploaded = st.file_uploader("📤 上传报价文件 (.xlsx，多选)", type="xlsx", accept_multiple_files=True)
    if uploaded:
        for f in uploaded:
            dest = UPLOAD_DIR / f.name
            if not dest.exists():
                dest.write_bytes(f.getvalue())
        st.success("✅ 上传完成")

    if st.button("开始清洗所有文件"):
        merged = []
        for path in sorted(UPLOAD_DIR.glob("*.xlsx")):
            key, tpl = match_template(extract_code(path.name))
            if not tpl: continue
            df0 = load_excel(path)
            merged.append(extract_data(df0, tpl, path.name))  # 使用文件名作为酒商
        if merged:
            df_clean = pd.concat(merged, ignore_index=True)
            df_clean.to_excel(CLEANED_PATH,index=False)
            st.success("✅ 清洗完成并保存")
            st.dataframe(df_clean.head(20),use_container_width=True)
            buf = BytesIO()
            df_clean.to_excel(buf,index=False)
            st.download_button("📥 下载清洗结果.xlsx",buf.getvalue(),file_name="cleaned_data.xlsx")
            st.session_state['df_clean'] = df_clean
        else:
            st.warning("⚠️ 未匹配到任何模板")

# —— 查询 页面 —— #
elif page == "查询":
    st.header("🔎 数据查询")
    if "df_clean" not in st.session_state:
        st.warning("请先在“清洗”页面完成清洗或上传清洗结果")
        st.stop()
    df_q = st.session_state["df_clean"]

    c1,c2,c3 = st.columns(3)
    with c1: kw = st.text_input("关键词","")
    with c2: sp = st.selectbox("供应商", ["全部"] + sorted(df_q["酒商"].dropna().unique().tolist()))
    with c3: yf = st.selectbox("年份", ["全部"] + sorted(df_q["年份"].dropna().astype(str).unique().tolist()))

    if st.button("查询"):
        df2 = df_q.copy()
        if kw:
            df2 = df2[df2.apply(lambda r:
                kw.lower() in str(r["酒名英文"]).lower() or
                kw.lower() in str(r["酒名中文"]).lower() or
                kw.lower() in str(r["年份"]), axis=1)]
        if sp!="全部":
            df2 = df2[df2["酒商"]==sp]
        if yf!="全部":
            df2 = df2[df2["年份"]==yf]
        if df2.empty:
            st.warning("❌ 无匹配记录")
        else:
            df2["_num"] = pd.to_numeric(df2["单价"].str.replace(r"[^0-9\.]","",regex=True),errors="coerce")
            df2 = df2.sort_values("_num")
            st.dataframe(df2[["酒名英文","酒名中文","年份","单价","支数","酒商"]]
                         .reset_index(drop=True),
                         use_container_width=True, height=600)

    if st.button("供应商详情"):
        st.session_state["show_supplier"] = not st.session_state.get("show_supplier", False)

    if st.session_state.get("show_supplier", False):
        st.markdown("---")
        st.subheader("🛠 供应商官网 & 源文件")
        supplier_files = sorted(UPLOAD_DIR.glob("*.xlsx"))
        supplier_names = [p.name for p in supplier_files]
        sel = st.selectbox("选择供应商（按文件名）", [""] + supplier_names, key="qs_sel")
        if sel:
            curr = supplier_info.get(sel,"")
            st.markdown(
                f"**🌐 官网：** <a href='{curr}' target='_blank'>{curr or '未设置'}</a>",
                unsafe_allow_html=True
            )
            newurl = st.text_input("编辑官网地址",value=curr,key="qs_url")
            if st.button("保存官网",key="qs_save"):
                supplier_info[sel] = newurl
                with open(SUPPLIER_INFO_PATH,"w",encoding="utf-8") as f:
                    json.dump(supplier_info,f,ensure_ascii=False,indent=2)
                st.success("✅ 官网已保存，刷新生效")
                st.rerun()

            st.markdown("---")
            st.subheader("📂 请选择要预览的源文件")
            paths = [p for p in sorted(UPLOAD_DIR.glob("*.xlsx")) if p.name == sel]
            if not paths:
                st.info("🚫 暂无该供应商的报价源文件")
            else:
                choice = st.selectbox("源文件", options=paths, format_func=lambda p: p.name, key="qs_file")
                if choice:
                    file_url   = f"{UPLOAD_URL_BASE}/{urllib.parse.quote(choice.name)}"
                    viewer_url = ("https://view.officeapps.live.com/op/embed.aspx?"
                                  "src="+urllib.parse.quote_plus(file_url))
                    st.markdown(f"[🔗 在线预览 {choice.name}]({viewer_url})",unsafe_allow_html=True)
                    components.iframe(viewer_url, height=400)

# —— 供应商管理 页面 —— #
else:
    st.header("📋 供应商管理")
    st.subheader("🔗 飞书多维表格")

    FEISHU_URL = "https://ncnqzrez82uj.feishu.cn/share/base/view/shrcnkNRRCJfdITTKXMxImgOQUc"

    html = f"""
    <style>
      #feishu_container {{ position: relative; width: 100%; height: 80vh; }}
      #feishu_iframe   {{ width: 100%; height: 100%; border: none; }}
      #fs_btn          {{ position: absolute; top: 10px; right: 10px;
                          padding: 6px 12px; background: white;
                          border: 1px solid #ccc; border-radius: 4px;
                          cursor: pointer; z-index: 999; }}
    </style>
    <div id="feishu_container">
      <button id="fs_btn" onclick="toggleFull()">全屏/退出</button>
      <iframe id="feishu_iframe"
              src="{FEISHU_URL}"
              allow="fullscreen"
              allowfullscreen>
      </iframe>
    </div>
    <script>
      function toggleFull() {{
        const el = document.getElementById('feishu_container');
        if (!document.fullscreenElement) {{
          el.requestFullscreen().catch(function(){{}});
        }} else {{
          document.exitFullscreen().catch(function(){{}});
        }}
      }}
    </script>
    """

    components.html(html, height=600)
