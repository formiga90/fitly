import pandas as pd
import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from ..app import app
from dash.dependencies import Input, Output, State
from ..api.sqlalchemy_declarative import fitbod, fitbod_muscles
from ..api.database import engine
import math
from datetime import datetime, timedelta, date
import dash_bootstrap_components as dbc
from ..utils import config, nextcloud_credentials_supplied


def get_layout(**kwargs):
    # Oura data required for home page
    if not nextcloud_credentials_supplied:
        return html.H1('Please provide nextcloud credentials in config', className='text-center')
    else:
        return html.Div([
            html.Div(className='row align-items-center text-center', children=[
                html.Div(className='col-lg-12 mt-2 mb-2', children=[
                    html.Div(id='lifting-date-buttons', children=[
                        dbc.Button('All Time', id='all-button', color='primary', style={'marginRight': '1vw'}),
                        dbc.Button('Year to Date', id='ytd-button', color='primary', style={'marginRight': '1vw'}),
                        dbc.Button('Last 6 Weeks', id='l6w-button', color='primary', style={'marginRight': '1vw'}),
                    ]),
                ]),
            ]),
            html.Div(id='lifting-header', className='row align-items-center text-center', children=[
                html.Div(className='col-lg-6 offset-md-3 mt-2 mb-2', children=[

                    dcc.Dropdown(id='muscle-options', className='bg-light',
                                 style={'backgroundColor': 'rgba(0,0,0,0)'},
                                 options=[
                                     {'label': 'Abs', 'value': 'Abs'},
                                     {'label': 'Back', 'value': 'Back'},
                                     {'label': 'Biceps', 'value': 'Biceps'},
                                     {'label': 'Chest', 'value': 'Chest'},
                                     {'label': 'Hamstrings', 'value': 'Hamstrings'},
                                     {'label': 'Lower Back', 'value': 'Lower Back'},
                                     {'label': 'Quadriceps', 'value': 'Quadriceps'},
                                     {'label': 'Shoulders', 'value': 'Shoulders'},
                                     {'label': 'Triceps', 'value': 'Triceps'}
                                 ],
                                 value=['Abs', 'Back', 'Biceps', 'Chest', 'Hamstrings', 'Lower Back', 'Quadriceps',
                                        'Shoulders', 'Triceps'],
                                 multi=True,
                                 placeholder='Select Muscle(s)...'
                                 )
                ]),
            ]),

            html.Div(className='row', children=[
                html.Div(id='exercise-containers', className='col-lg-12')

            ])
        ])


white = config.get('oura', 'white')
teal = config.get('oura', 'teal')
light_blue = config.get('oura', 'light_blue')
dark_blue = config.get('oura', 'dark_blue')
orange = config.get('oura', 'orange')
ftp_color = 'rgb(100, 217, 236)'


def generate_exercise_charts(timeframe, muscle_options, metric='1RM', sort_ascending=True):
    df = pd.read_sql(sql=app.session.query(fitbod).statement, con=engine)

    # Merge 'muscle' into exercise table for mapping
    df_muscle = pd.read_sql(sql=app.session.query(fitbod_muscles).statement, con=engine)
    df = df.merge(df_muscle, how='left', left_on='Exercise', right_on='Exercise')
    app.session.remove()

    # Filter on selected msucles
    df = df[df['Muscle'].isin(muscle_options)]

    # Filter on selected date range
    if timeframe == 'ytd':
        df = df[df['date_UTC'].dt.date >= date(datetime.today().year, 1, 1)]
    elif timeframe == 'l6w':
        df = df[df['date_UTC'].dt.date >= (datetime.now().date() - timedelta(days=42))]

    if len(df) > 0:
        if metric == '1RM':
            # Calculate 1RM for exercise that have both weight and reps
            df_1rm = df[(df['Weight']) > 0 & (df['Reps'] > 0)]
            # Calculate Brzycki 1RM based off last 6 weeks of workouts
            df_1rm['1RM'] = (df_1rm['Weight'] * (36 / (37 - df_1rm['Reps'])))
            df_1rm['1RM_Type'] = '1RM (lbs)'

            # Show total Reps for exercises with no weight (where 1RM can't be calculated)
            df_reps = df[(df['Weight'] == 0) & (df['Reps'] != 0) & (df['Duration'] == 0)]
            df_reps['1RM'] = df_reps['Reps']
            df_reps['1RM_Type'] = 'Reps'
            # Remove exercises which have sets both with and without weight to avoid skewing % increases
            df_reps = df_reps[~df_reps['Exercise'].isin(df_1rm['Exercise'].unique())]

            # Show total volume (duration * weight) for time-based exercises (don't have reps so 1RM can't be calculated)
            df_duration = df[(df['Weight'] == 0) & (df['Reps'] == 0) & (df['Duration'] != 0)]
            df_duration['1RM'] = df_duration['Duration'] * df['Weight'].replace(0, 1)
            df_duration['1RM_Type'] = 'Volume'

            # Consolidate dfs
            df = pd.concat([df_1rm, df_reps, df_duration], ignore_index=True)
            # Get max from each set
            df = df.groupby(['date_UTC', 'Exercise', '1RM_Type'])['1RM'].max().reset_index()

            # Sort by # change
            for exercise in df['Exercise'].sort_values().unique():
                df_temp = df[df['Exercise'] == exercise]
                df.at[df['Exercise'] == exercise, '% Change'] = ((df_temp[metric].tail(1).values[0] -
                                                                  df_temp[metric].head(1).values[0]) /
                                                                 df_temp[metric].head(1).values[0]) * 100

        # # TODO: Add toggle for this? Currently front end hardcoded to 1RM
        # elif metric == 'Volume':
        #     # Calculate Volume and aggregate to the daily (workout) level
        #     df['Volume'] = df['Reps'].replace(0, 1) * df['Weight'].replace(0, 1) * df['Duration'].replace(0, 1)
        #     df = df.groupby(['date_UTC', 'Exercise'])['Volume'].sum().reset_index()

        # Sort exercises by areas which have least improvement on a % basis
        df = df.sort_values(by='% Change', ascending=sort_ascending)

        widgets = []
        for exercise in df['Exercise'].unique():
            df_temp = df[df['Exercise'] == exercise]
            # Only plot exercise if at least 2 different dates with that exercise
            if len(df_temp['date_UTC'].unique()) > 1:
                try:
                    backgroundColor = 'border-danger' if df_temp['% Change'].values[0] < 0 else 'border-success' if \
                        df_temp['% Change'].values[0] > 0 else ''
                except:
                    backgroundColor = ''

                # Sort by date ascending
                df_temp = df_temp.sort_values(by=['date_UTC'])
                # Calculate trend of each data point vs starting point
                df_temp['% Change'] = df_temp[metric].apply(
                    lambda x: ((x - df_temp[metric].head(1)) / df_temp[metric].head(1)) * 100)
                tooltip = [df_temp['1RM_Type'].iloc[
                               0] + ':<b>{:.0f} </b>({}{:.1f}%)'.format(x, '+' if y >= 0 else '', y) for (x, y) in
                           zip(df_temp[metric], df_temp['% Change'])]

                widgets.append([exercise, backgroundColor,
                                dcc.Graph(id=exercise + '-trend',
                                          style={'height': '100%'},
                                          config={'displayModeBar': False, },
                                          figure={
                                              'data': [
                                                  go.Scatter(
                                                      x=df_temp['date_UTC'],
                                                      y=df_temp['% Change'],
                                                      mode='lines+markers',
                                                      text=tooltip,
                                                      hoverinfo='x+text',
                                                      opacity=0.7,
                                                      line={'color': teal}
                                                  ),
                                              ],
                                              'layout': go.Layout(
                                                  height=150,
                                                  font=dict(
                                                      color='rgb(220,220,220)',
                                                      size=10,
                                                  ),

                                                  # hoverlabel={'font': {'size': 10}},
                                                  xaxis=dict(
                                                      showline=True,
                                                      color='rgb(220,220,220)',
                                                      showgrid=False,
                                                      showticklabels=True,
                                                      tickformat='%b %d',
                                                      # Specify range to get rid of auto x-axis padding when using scatter markers
                                                      # range=[df.index.max() - timedelta(days=41),
                                                      #        df.index.max()],
                                                      # rangeselector=dict(
                                                      #     bgcolor='rgb(66, 66, 66)',
                                                      #     bordercolor='#d4d4d4',
                                                      #     borderwidth=.5,
                                                      #     buttons=buttons,
                                                      #     xanchor='center',
                                                      #     x=.5,
                                                      #     y=1,
                                                      # ),
                                                  ),
                                                  yaxis=dict(
                                                      showgrid=False,
                                                      showticklabels=False,
                                                      gridcolor='rgb(73, 73, 73)',
                                                      gridwidth=.5,
                                                      # tickformat='%',

                                                  ),
                                                  margin={'l': 0, 'b': 25, 't': 20, 'r': 0},
                                                  showlegend=False,
                                                  annotations=[
                                                      go.layout.Annotation(
                                                          font={'size': 14},
                                                          x=df_temp.loc[df_temp['date_UTC'].idxmax()]['date_UTC'],
                                                          y=df_temp.loc[df_temp['date_UTC'].idxmax()]['% Change'],
                                                          xref="x",
                                                          yref="y",
                                                          text="{:.1f}%".format(
                                                              df_temp.loc[df_temp['date_UTC'].idxmax()]['% Change']),
                                                          showarrow=True,
                                                          arrowhead=0,
                                                          arrowcolor=white,
                                                          ax=5,
                                                          ay=-20
                                                      )
                                                  ],
                                                  hovermode='x',
                                                  autosize=True,
                                                  # title=exercise
                                              )
                                          })
                                ])

        widgets = [
            html.Div(className='col-lg-2 mb-3', children=[
                dbc.Card(className=backgroundColor, children=[
                    dbc.CardHeader(exercise),
                    dbc.CardBody(chart)
                ])]
                     ) for exercise, backgroundColor, chart in widgets]

        # Set up each div of 6 graphs to be placed in
        num_divs = math.ceil(len(widgets) / 6)
        div_layout = []
        for i in range(0, num_divs):
            children = []
            for widget in widgets[:6]:
                children.append(widget)
                widgets.remove(widget)

            div_layout.append(html.Div(className='row', children=children))
            # div_layout.append(
            #     html.Div(className='row'))

        return div_layout


# Group power profiles
@app.callback([Output('exercise-containers', 'children'),
               Output('all-button', 'style'),
               Output('ytd-button', 'style'),
               Output('l6w-button', 'style')],
              [Input('muscle-options', 'value'),
               Input('all-button', 'n_clicks'),
               Input('ytd-button', 'n_clicks'),
               Input('l6w-button', 'n_clicks')],
              [State('all-button', 'style'),
               State('ytd-button', 'style'),
               State('l6w-button', 'style')]
              )
def update_exercise_charts(muscle_options, all_n_clicks, ytd_n_clicks, l6w_n_clicks, all_style, ytd_style, l6w_style):
    latest_dict = {'all-button': 'all', 'ytd-button': 'ytd', 'l6w-button': 'l6w'}
    style = {'all': {'marginRight': '1vw'}, 'ytd': {'marginRight': '1vw'}, 'l6w': {'marginRight': '1vw'}}
    ctx = dash.callback_context
    if not ctx.triggered:
        latest = 'ytd'
    elif ctx.triggered[0]['prop_id'] == 'muscle-options.value':
        for key, value in {'all': all_style, 'ytd': ytd_style, 'l6w': l6w_style}.items():
            if value == {'marginRight': '1vw', 'color': '#64D9EC', 'borderColor': '#64D9EC'}:
                latest = key
    else:
        latest = latest_dict[ctx.triggered[0]['prop_id'].split('.')[0]]

    style[latest] = {'marginRight': '1vw', 'color': '#64D9EC', 'borderColor': '#64D9EC'}

    return generate_exercise_charts(timeframe=latest, muscle_options=muscle_options), style['all'], style['ytd'], style[
        'l6w']
