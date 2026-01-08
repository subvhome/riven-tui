from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual_plotext import PlotextPlot

# Actual data snippet from your previous message
MEDIA_YEAR_RELEASES = [
    {"year": 1995, "count": 27}, {"year": 1996, "count": 27}, {"year": 1997, "count": 41},
    {"year": 1998, "count": 49}, {"year": 1999, "count": 44}, {"year": 2000, "count": 48},
    {"year": 2001, "count": 61}, {"year": 2002, "count": 55}, {"year": 2003, "count": 76},
    {"year": 2004, "count": 45}, {"year": 2005, "count": 37}, {"year": 2006, "count": 27},
    {"year": 2007, "count": 29}, {"year": 2008, "count": 28}, {"year": 2009, "count": 27},
    {"year": 2010, "count": 29}, {"year": 2011, "count": 48}, {"year": 2012, "count": 49},
    {"year": 2013, "count": 95}, {"year": 2014, "count": 58}, {"year": 2015, "count": 82},
    {"year": 2016, "count": 66}, {"year": 2017, "count": 46}, {"year": 2018, "count": 64},
    {"year": 2019, "count": 122}, {"year": 2020, "count": 56}, {"year": 2021, "count": 111},
    {"year": 2022, "count": 133}, {"year": 2023, "count": 114}, {"year": 2024, "count": 172},
    {"year": 2025, "count": 454}, {"year": 2026, "count": 46}
]

STATES_DATA = {
    "Unknown": 48, "Unreleased": 52, "Ongoing": 28, "Indexed": 153,
    "Completed": 2117, "PartiallyCompleted": 14, "Paused": 13
}

class TestGraphApp(App):
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield PlotextPlot(id="release-graph")
            yield PlotextPlot(id="state-graph")

    def on_mount(self) -> None:
        # Test Release Graph
        graph = self.query_one("#release-graph", PlotextPlot)
        plt = graph.plt
        plt.clear_figure()
        plt.theme("dark")
        x = [d["year"] for d in MEDIA_YEAR_RELEASES]
        y = [d["count"] for d in MEDIA_YEAR_RELEASES]
        plt.bar(x, y, color="cyan")
        plt.title("Isolated Test: Releases by Year")
        graph.refresh()

        # Test States Graph
        state_graph = self.query_one("#state-graph", PlotextPlot)
        plt_s = state_graph.plt
        plt_s.clear_figure()
        plt_s.theme("dark")
        labels = list(STATES_DATA.keys())
        values = list(STATES_DATA.values())
        plt_s.bar(labels, values, color="magenta", orientation="horizontal")
        plt_s.title("Isolated Test: States")
        state_graph.refresh()

if __name__ == "__main__":
    TestGraphApp().run()
