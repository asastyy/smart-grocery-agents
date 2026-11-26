"""Paged recipe browser backed by SQLite; never load the whole catalogue in UI."""
import math
import streamlit as st

from smart_grocery.catalog.database import DEFAULT_DB,database_report,ensure_database,get_recipe,search_catalog

ISSUES={
 'unresolved_quantities_or_units':'Не все количества и единицы определены',
 'unknown_servings':'Не указано точное число порций',
 'unknown_total_time':'Не указано однозначное время',
 'source_quality_warning':'Источник помечен как требующий доработки',
 'additional_wait_time_requires_review':'В инструкции есть дополнительное ожидание',
 'unresolved_instruction_template':'Нужна проверка разметки инструкции',
 'ingredient_quantity_alignment':'Количество позиций и количеств в источнике различается',
 'unknown_ingredient':'Часть ингредиентов неизвестна',
 'partial_instructions':'Инструкция неполная',
 'unsupported_ingredient_structure':'Структуру ингредиентов нужно проверить',
}
MODES={'Все рецепты':'all','Есть порции и время':'metadata','Все количества определены':'quantified','Без структурных блокеров':'ready'}


@st.cache_data(ttl=60,show_spinner=False)
def cached_search(query,provider,quality,page,db_mtime):
    return search_catalog(query,provider,quality,page=page)


def render_catalog():
    st.subheader('Рецепты')
    if not DEFAULT_DB.exists() and list(DEFAULT_DB.parent.glob('catalog*.building.sqlite')):
        st.info('Идет подготовка поискового индекса каталога.');return
    path=ensure_database()
    report=database_report(path)
    totals=report['by_source']
    a,b,c=st.columns(3)
    a.metric('В каталоге',f"{report['catalog_records']:,}".replace(',',' '))
    b.metric('С инструкциями',f"{sum(x['has_instructions'] for x in totals.values()):,}".replace(',',' '))
    c.metric('Без структурных блокеров',sum(x['planning_ready'] for x in totals.values()))
    st.caption('Food.com и Wikibooks · импортированные рецепты. Безопасность при аллергиях не подтверждена.')
    if 'sample' in report['source_scope'].casefold():
        st.caption('Загружена автономная выборка Food.com. Полный каталог: python scripts/build_catalog_db.py --download')
    query=st.text_input('Поиск по названию или ингредиенту',key='catalog_query')
    left,right=st.columns(2)
    source=left.selectbox('Источник',['Все источники',*sorted(totals)])
    mode=right.selectbox('Полнота данных',list(MODES))
    signature=(query,source,mode)
    if st.session_state.get('catalog_signature')!=signature:
        st.session_state.catalog_page=1;st.session_state.catalog_signature=signature
    provider=None if source=='Все источники' else source
    # Read one page of titles, then a single selected recipe; JSON stays on disk.
    page=int(st.session_state.get('catalog_page',1))
    total,rows=cached_search(query,provider,MODES[mode],page,path.stat().st_mtime_ns)
    if not total:
        st.info('Рецепты не найдены.');return
    pages=math.ceil(total/50)
    page=int(st.number_input('Страница',min_value=1,max_value=max(1,pages),step=1,key='catalog_page'))
    if page!=int(st.session_state.get('catalog_rendered_page',0)):
        total,rows=cached_search(query,provider,MODES[mode],page,path.stat().st_mtime_ns)
    st.session_state.catalog_rendered_page=page
    st.caption(f'Найдено: {total:,} · страница {page} из {pages}'.replace(',',' '))
    labels={r['recipe_id']:r['title']+' · '+r['provider'] for r in rows}
    selected=st.selectbox('Блюдо',list(labels),format_func=labels.get)
    recipe=get_recipe(selected,path)
    if recipe is None:return
    st.markdown(f"### {recipe['title']}")
    servings=recipe['servings'] or 'не указаны'
    minutes=f"{recipe['cook_minutes']} мин" if recipe['cook_minutes'] is not None else 'не указано'
    st.caption(f'Порции: {servings} · Время по источнику: {minutes}')
    if recipe['quality']['issues']:st.warning(' · '.join(ISSUES.get(x,x) for x in recipe['quality']['issues']))
    if recipe['provenance']['provider']=='Food.com':
        st.caption('В исходной выгрузке многие количества не имеют единиц. Число без единицы не считается штуками.')
    st.markdown('#### Ингредиенты')
    for item in recipe['ingredient_details']:st.write('• '+item['text'])
    st.markdown('#### Приготовление')
    for n,step in enumerate(recipe['instructions'] or [],1):st.write(f'{n}. {step}')
    st.link_button('Открыть источник',recipe['source'])
    with st.expander('Качество и происхождение данных'):
        st.write('Ручная проверка: не выполнена. Аллергены: неизвестны.')
        st.json({'source':recipe['provenance'],'quality':recipe['quality'],'ingredients':recipe['ingredient_details']})
