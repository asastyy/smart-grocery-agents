"""Browse the extended source-aware catalogue without changing MVP planning."""
import streamlit as st

from smart_grocery.catalog.loader import load_catalog

UNITS={'g':'г','ml':'мл','pcs':'шт.'}
ISSUES={
 'unresolved_quantities_or_units':'Не все количества и единицы определены',
 'unknown_servings':'Не указано точное число порций',
 'unknown_total_time':'Не указано однозначное время',
 'source_quality_warning':'Источник помечен как требующий доработки',
 'additional_wait_time_requires_review':'В инструкции есть дополнительное ожидание',
 'unresolved_instruction_template':'Нужна проверка разметки инструкции',
}


def render_catalog():
    records=load_catalog()
    st.subheader('Рецепты')
    a,b,c=st.columns(3)
    a.metric('В каталоге',len(records))
    b.metric('С инструкциями',sum(bool(r['instructions']) for r in records))
    c.metric('В выборке для проверки',min(50,len(records)))
    st.caption('Wikibooks · CC BY-SA 4.0 · каталог импортирован автоматически. Безопасность при аллергиях не подтверждена.')
    query=st.text_input('Поиск по названию',key='catalog_query')
    mode=st.selectbox('Полнота данных',['Все рецепты','Есть порции и время','Все количества определены'])
    matches=[r for r in records if query.casefold() in r['title'].casefold()]
    if mode=='Есть порции и время':matches=[r for r in matches if r['servings'] is not None and r['cook_minutes'] is not None]
    if mode=='Все количества определены':matches=[r for r in matches if len(r['ingredients'])==len(r['ingredient_details'])]
    if not matches:
        st.info('Рецепты не найдены.');return
    selected=st.selectbox('Блюдо',[r['recipe_id'] for r in matches],format_func=lambda rid:next(r['title'] for r in matches if r['recipe_id']==rid))
    recipe=next(r for r in matches if r['recipe_id']==selected)
    st.markdown(f"### {recipe['title']}")
    servings=recipe['servings'] or 'не указаны'
    minutes=f"{recipe['cook_minutes']} мин" if recipe['cook_minutes'] is not None else 'не указано'
    st.caption(f'Порции: {servings} · Время по источнику: {minutes}')
    if recipe['quality']['issues']:st.warning(' · '.join(ISSUES.get(x,x) for x in recipe['quality']['issues']))
    st.markdown('#### Ингредиенты')
    for item in recipe['ingredient_details']:
        st.write('• '+item['text'])
    st.markdown('#### Приготовление')
    for n,step in enumerate(recipe['instructions'] or [],1):st.write(f'{n}. {step}')
    st.link_button('Рецепт и авторы в Wikibooks',recipe['source'])
    with st.expander('Качество и происхождение данных'):
        st.write('Ручная проверка: не выполнена. Аллергены: неизвестны.')
        st.json({'source':recipe['provenance'],'quality':recipe['quality'],'ingredients':recipe['ingredient_details']})
