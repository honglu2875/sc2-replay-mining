from bokeh.io import output_notebook, reset_output
from bokeh.models import Span, Range1d, Legend, BoxAnnotation, HoverTool, Arrow, NormalHead
from bokeh.plotting import figure, show, gridplot, ColumnDataSource


def merge(i, last_entry, sign=None, length=3):
    if last_entry is not None:
        if sign is not None:
            # Check to see if this is a continuation
            if last_entry[1] == i + length - 1 and last_entry[2] == sign:
                return [(last_entry[0], i + length, sign)]
            else:
                return [last_entry, (i, i + length, sign)]
        else:
            # Check to see if this is a continuation
            if last_entry[1] == i + length - 1:
                return [(last_entry[0], i + length)]
            else:
                return [last_entry, (i, i + length)]
    else:
        if sign is not None:
            return [(i, i + length, sign)]
        else:
            return [(i, i + length)]


def detect_nelson_bias(src_data, x_bar):
    # Bias is defined as 9 or more consecutive points sitting above or below our x-bar line
    bias_ranges = []
    length = 9
    for i in range(len(src_data) - length):
        last_entry = bias_ranges.pop() if len(bias_ranges) > 0 else None
        if all([src_data[k] > x_bar for k in range(i, i + length)]):
            sign = "+"
            bias = merge(i, last_entry, sign=sign, length=length)
            bias_ranges.extend(bias)
        elif all([src_data[k] < x_bar for k in range(i, i + length)]):
            sign = "-"
            bias = merge(i, last_entry, sign=sign, length=length)
            bias_ranges.extend(bias)
        else:
            if last_entry:
                bias_ranges.append(last_entry)

    return bias_ranges


def detect_nelson_trend(src_data, std):
    # Trend is defined as 6 or more consecutive points all increasing or decreasing (or 6 or more consecutive non(increasing, decreasing) where difference between start and end points greater than 1.5 standard deviations )
    trend_ranges = []
    length = 6
    for i in range(len(src_data) - length):
        last_entry = trend_ranges.pop() if len(trend_ranges) > 0 else None
        if (all(x < y
                for x, y in zip(src_data[i:i + length], src_data[i + 1:i +
                                                                 length])) or
            (all(x <= y
                 for x, y in zip(src_data[i:i + length], src_data[i + 1:i +
                                                                  length]))
             and abs(src_data[i] - src_data[i + length]) >= 1.5 * std)):
            sign = "+"
            trend_ranges.extend(merge(i, last_entry, sign=sign, length=length))
        elif (all(x > y
                  for x, y in zip(src_data[i:i + length], src_data[i + 1:i +
                                                                   length])) or
              (all(x >= y
                   for x, y in zip(src_data[i:i + length], src_data[i + 1:i +
                                                                    length]))
               and abs(src_data[i] - src_data[i + length]) >= 1.5 * std)):
            sign = "-"
            trend_ranges.extend(merge(i, last_entry, sign=sign, length=length))
        else:
            if last_entry:
                trend_ranges.append(last_entry)

    return trend_ranges


def detect_nelson_oscillation(src_data):
    # Oscillation is defined as 14 or more consecutive points, all alternating in direction
    diff = lambda x, y: 1 if y - x > 0 else -1 if y - x < 0 else None
    oscillation_ranges = []
    length = 14
    deltas = []
    for i in range(len(src_data) - length):
        last_entry = oscillation_ranges.pop(
        ) if len(oscillation_ranges) > 0 else None
        sign = None
        is_oscillating = True
        for curr in range(i, i + length - 1):
            if sign == None and curr == i:
                sign = diff(src_data[curr], src_data[curr + 1])
            elif sign is None and curr != i:
                is_oscillating = False
                break
            else:
                new_sign = diff(src_data[curr], src_data[curr + 1])
                if new_sign is None or new_sign == sign:
                    is_oscillating = False
                    break
                elif new_sign != sign and new_sign is not None:
                    sign = new_sign
        if is_oscillating:
            # check if this is a continuation of a previous oscillation
            oscillation_ranges.extend(merge(i, last_entry, length=length))

        else:
            if last_entry:
                oscillation_ranges.append(last_entry)

    return oscillation_ranges


def avg_last_minute(process, pid, time, replay):
    data = pd.DataFrame(
        {"Data": [k[1] for k in replay.stats[pid - 1][process]]},
        index=[int(k[0] / 16) for k in replay.stats[pid - 1][process]])

    rolling = data.rolling(6).mean()
    pct_change = data.pct_change()
    ndx = data.index.get_loc(time, method="ffill")

    prev_ndx = max(ndx - 1, 0)
    print(ndx, prev_ndx)
    r_mean = rolling.get_value(rolling.index[ndx], "Data")
    prev_mean = rolling.get_value(rolling.index[prev_ndx], "Data")
    print(r_mean, prev_mean)
    print(pct_change)
    pcng = pct_change.get_value(rolling.index[ndx], "Data")

    change = "⬆️" if r_mean > prev_mean else "⬇️" if r_mean < prev_mean else ""

    return r_mean if not pd.isnull(r_mean) else 0, change, pcng if not (
        pd.isnull(pcng) or pcng != np.Inf) else 0


# Define Nelson Rules Chart Generator
def nelson_rules_chart_generator(src,
                                 timeseries,
                                 player,
                                 pid,
                                 process_name,
                                 unit_name,
                                 replay,
                                 plot_width=350,
                                 fill_color="blue",
                                 line_color="blue",
                                 line_width=2,
                                 annotations=None,
                                 fixed_lcl=None,
                                 fixed_ucl=None):
    # We strip the first two data points (first data point is 0 and second data point should roughly be the same for all games)
    x_bar = src[2:].mean()
    std = src[2:].std()
    ctrl_limits = [x_bar + (k * std) for k in range(-3, 4)]
    ctrl_labels = ["LCL", "-2σ", "-1σ", "x-bar", "1σ", "2σ", "UCL"]
    ctrl_colors = [
        "#55597F", "#5D6DFF", "#A9B2FF", "#000000", "#FF9E9F", "#FF5253",
        "#7F2929"
    ]
    ctrl_dash = [
        "solid", "dashed", "dashed", "solid", "dashed", "dashed", "solid"
    ]
    ctrl_legend = [
        "{0} - {1:10.4f}".format(cl[0], cl[1])
        for cl in zip(ctrl_labels, ctrl_limits)
    ]
    ctrl_width = [3, 2, 2, 3, 2, 2, 3]

    significant = lambda x: x > ctrl_limits[5] or x < ctrl_limits[1]

    hover = HoverTool(tooltips=[("time", "@x"), ("value", "@y")])

    p = figure(plot_width=plot_width,
               plot_height=300,
               x_axis_label="Game Time (in seconds)",
               y_axis_label=unit_name,
               tools=[hover],
               toolbar_location="above")
    # Generate control lines
    lines = []
    source = ColumnDataSource(data=dict(
        x=[x / 16 for x in timeseries],
        y=src,
        alpha=[
            1 if significant(y) and ndx > 2 else 0.7
            for ndx, y in enumerate(src)
        ],
        radius=[
            6 if significant(y) and ndx > 2 else 4 for ndx, y in enumerate(src)
        ],
    ))
    for ndx, cl in enumerate(ctrl_limits):
        limit = cl

        lines.append(
            p.line([x / 16 for x in timeseries], [limit] * len(timeseries),
                   line_width=ctrl_width[ndx],
                   line_dash=ctrl_dash[ndx],
                   tags=[
                       ctrl_labels[ndx] if k == 0 else None
                       for k, _ in enumerate(timeseries)
                   ],
                   line_color=ctrl_colors[ndx]))

    p.circle("x",
             "y",
             source=source,
             alpha="alpha",
             radius="radius",
             fill_color=fill_color,
             line_width=line_width)

    # Handle bias
    bias_ranges = detect_nelson_bias(src, x_bar)
    for rng in bias_ranges:
        if rng[2] is "+":
            p.add_layout(
                BoxAnnotation(bottom=x_bar,
                              top=ctrl_limits[-1],
                              left=timeseries[rng[0]] / 16,
                              right=timeseries[rng[1]] / 16,
                              fill_color="green"))
        elif rng[2] is "-":
            p.add_layout(
                BoxAnnotation(top=x_bar,
                              bottom=ctrl_limits[0],
                              left=timeseries[rng[0]] / 16,
                              right=timeseries[rng[1]] / 16,
                              fill_color="red"))

    # Handle trends
    trend_ranges = detect_nelson_trend(src, std)
    for rng in trend_ranges:
        if rng[2] is "+":
            p.add_layout(
                Arrow(end=NormalHead(line_color="goldenrod",
                                     fill_color="goldenrod"),
                      x_start=timeseries[rng[0]] / 16,
                      y_start=src[rng[0]],
                      x_end=timeseries[rng[1]] / 16,
                      y_end=src[rng[1]],
                      line_width=4,
                      line_alpha=0.6,
                      line_dash="solid"))
        elif rng[2] is "-":
            p.add_layout(
                Arrow(end=NormalHead(line_color="#7F0000",
                                     fill_color="#7F0000"),
                      x_start=timeseries[rng[0]] / 16,
                      y_start=src[rng[0]],
                      x_end=timeseries[rng[1]] / 16,
                      y_end=src[rng[1]],
                      line_width=4,
                      line_alpha=0.6,
                      line_dash="solid"))

    p.title.text = "{0} for {1}".format(unit_name, player)
    p.y_range = p.y_range = Range1d(ctrl_limits[0] - 0.125 * ctrl_limits[0],
                                    1.125 * ctrl_limits[-1])

    legend = Legend(items=list(zip(ctrl_legend, [[l] for l in lines])),
                    location=(10, -30))
    p.add_layout(legend, "right")

    return p, ctrl_limits, min(src[2:]), max(src[2:]), timeseries[-1]
