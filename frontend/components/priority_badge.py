from PySide6.QtWidgets import QLabel, QSizePolicy


class PriorityBadge(QLabel):

    def __init__(self, priority="Green"):
        super().__init__()

        self.setAlignment(
            self.alignment()
        )

        self.setMinimumWidth(64)
        self.setMaximumWidth(110)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setWordWrap(False)

        self.set_priority(
            priority
        )

    # ====================================
    # SET PRIORITY
    # ====================================

    def set_priority(self, priority):

        raw = str(priority or "Medium").strip()
        normalized = raw.replace("_", " ").replace("-", " ").title()
        aliases = {
            "High": "Red",
            "Critical": "Red",
            "Urgent": "Red",
            "Medium High": "Orange",
            "Normal": "Yellow",
            "Low": "Green",
        }
        self.priority = aliases.get(normalized, normalized)
        self.setText(self.priority)

        if self.priority == "Red":

            self.setStyleSheet("""
                QLabel {
                    background-color: #FEE2E2;
                    color: #991B1B;
                    border-radius: 6px;
                    padding: 5px 10px;
                    font-weight: bold;
                }
            """)

        elif self.priority == "Orange":

            self.setStyleSheet("""
                QLabel {
                    background-color: #FFEDD5;
                    color: #9A3412;
                    border-radius: 6px;
                    padding: 5px 10px;
                    font-weight: bold;
                }
            """)

        elif self.priority == "Yellow":

            self.setStyleSheet("""
                QLabel {
                    background-color: #FEF3C7;
                    color: #92400E;
                    border-radius: 6px;
                    padding: 5px 10px;
                    font-weight: bold;
                }
            """)

        else:

            self.setStyleSheet("""
                QLabel {
                    background-color: #DCFCE7;
                    color: #166534;
                    border-radius: 6px;
                    padding: 5px 10px;
                    font-weight: bold;
                }
            """)