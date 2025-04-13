import streamlit as st
st.set_page_config(page_title="红酒查价系统 - 登录 + 查价权限", page_icon="🍷")

import pandas as pd
import os
from datetime import datetime
from io import BytesIO

@st.cache_data
def load_column_template(file_path="字段模板.xlsx"):
    try:
        df = pd.read_excel(file_path)
        column_map = {}
        for _, row in df.iterrows():
            supplier = row["供货商名"]
            mapping = {}
            for field in [
                "酒名英文字段", "酒名中文字段", "年份字段",
                "单价字段", "散支字段", "整箱字段",
                "整箱规格字段", "净含量字段", "官网链接"
            ]:
                if pd.notna(row.get(field, "")):
                    mapping[field] = row[field]
            if mapping:
                column_map[supplier] = mapping
        return column_map
    except Exception as e:
        st.error(f"字段模板读取失败：{e}")
        return {}

@st.cache_data
def load_users(file_path="users.xlsx"):
    try:
        df = pd.read_excel(file_path)
        return df.set_index("用户名").to_dict("index")
    except Exception as e:
        st.error(f"用户账号读取失败：{e}")
        return {}

users = load_users()
column_template = load_column_template()

UPLOAD_DIR = "data_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

st.title("🍷 红酒查价系统 - 登录")

if "user" not in st.session_state:
    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")

        if submitted:
            if username in users and users[username]["密码"] == password:
                st.session_state.user = username
                st.session_state.role = users[username]["角色"]
                st.rerun()
            else:
                st.error("用户名或密码错误")

if "user" in st.session_state:
    st.success(f"欢迎你，{st.session_state.user}（{st.session_state.role}）")
    role = st.session_state.role

    if "all_data" not in st.session_state:
        st.session_state.all_data = []

    for filename in os.listdir(UPLOAD_DIR):
        if filename.endswith(".xlsx"):
            path = os.path.join(UPLOAD_DIR, filename)
            try:
                df_old = pd.read_excel(path)
                if not df_old.empty:
                    st.session_state.all_data.append(df_old)
            except Exception:
                continue

    supplier = st.selectbox("请选择上传的供货商：", [""] + list(column_template.keys()))
    file = st.file_uploader("上传报价文件（.xlsx）", type=["xlsx"])

    if supplier and file:
        try:
            preview_df = pd.read_excel(file, nrows=10, header=None)
            header_row_index = preview_df.apply(lambda row: row.astype(str).str.contains("酒|wine", case=False).any(), axis=1)
            first_header = header_row_index.idxmax() if header_row_index.any() else 0
            df_raw = pd.read_excel(file, header=first_header)
            field_map = column_template[supplier]

            renamed = {}
            for std_col, orig_cols in field_map.items():
                if "+" in orig_cols:
                    parts = [col.strip() for col in orig_cols.split("+")]
                    combined = df_raw[parts[0]].astype(str) if parts[0] in df_raw.columns else ""
                    for p in parts[1:]:
                        if p in df_raw.columns:
                            combined += " " + df_raw[p].astype(str)
                    renamed[std_col] = combined
                elif orig_cols in df_raw.columns:
                    renamed[std_col] = df_raw[orig_cols]
                else:
                    renamed[std_col] = ""

            df_clean = pd.DataFrame(renamed)
            df_clean["供货商"] = supplier
            df_clean["供货商代码"] = supplier.split("(")[-1].replace(")", "")
            df_clean["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df_clean["官网链接"] = field_map.get("官网链接", "")

            st.session_state.all_data.append(df_clean)

            save_path = os.path.join(UPLOAD_DIR, f"{supplier}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx")
            df_clean.to_excel(save_path, index=False)

            st.success(f"✅ 成功读取并映射字段，共 {len(df_clean)} 条记录")
            st.dataframe(df_clean)

        except Exception as e:
            st.error(f"❌ 文件读取失败：{e}")
    elif file and not supplier:
        st.warning("⚠️ 请先选择供货商再上传文件。")

    if st.session_state.all_data:
        df_all = pd.concat(st.session_state.all_data, ignore_index=True)
        st.subheader("📊 汇总比价结果")

        keyword = st.text_input("🔍 输入关键词（酒名/年份/供货商）进行筛选：")
        if keyword:
            df_all = df_all[df_all.astype(str).apply(lambda row: row.str.contains(keyword, case=False)).any(axis=1)]

        if "酒名英文字段" in df_all.columns and "年份字段" in df_all.columns and "单价字段" in df_all.columns:
            df_all = df_all[df_all["年份字段"].notna()]
            df_all["比价键"] = df_all["酒名英文字段"].astype(str) + "_" + df_all["年份字段"].astype(str)
            df_all["单价字段"] = pd.to_numeric(df_all["单价字段"], errors="coerce")
            if not df_all.empty:
               df_all["是否最低价"] = ""

try:
    idx_min_price = df_all.groupby("比价键")["单价字段"].idxmin()
    idx_min_price = idx_min_price.dropna().astype("Int64")  # 去除无效行
    df_all.loc[idx_min_price, "是否最低价"] = "✅ 最低"
except Exception as e:
    st.warning(f"⚠️ 无法标记最低价：{e}")

            else:
                st.warning("⚠️ 当前没有有效年份的数据参与比价，表格为空。")
        else:
            st.warning("比价功能依赖字段：酒名英文字段、年份字段、单价字段，请确保它们存在。")

        def render_link(row):
            url = row.get("官网链接", "")
            return f'<a href="{url}" target="_blank">🔗 官网</a>' if url else ""

        df_all["跳转官网"] = df_all.apply(render_link, axis=1)

        if role == "销售":
            columns_to_show = [
                "酒名英文字段", "酒名中文字段", "年份字段", "单价字段",
                "散支字段", "整箱字段", "整箱规格字段", "净含量字段",
                "是否最低价", "供货商代码"
            ]
        else:
            columns_to_show = df_all.columns.tolist()

        st.write("✅ 下方可点击跳转供货商官网")
        st.write(df_all[columns_to_show].to_html(escape=False), unsafe_allow_html=True)

        def convert_df(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.drop(columns=["跳转官网"], errors="ignore").to_excel(writer, index=False, sheet_name='报价比价')
                writer.save()
            return output.getvalue()

        excel_bytes = convert_df(df_all[columns_to_show])
        st.download_button(
            label="📥 下载比价结果 Excel",
            data=excel_bytes,
            file_name="比价结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
