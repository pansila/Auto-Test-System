from io import BytesIO
from io import StringIO

import mistune

KEYWORDS = ["setting", "settings", "variable", "variables", "test case", "test cases", "keyword", "keywords"]

def robotize(file_path):
    with open(file_path) as md_file:
        robot_data = StringIO()
        robot_lines = []
        #print('\n========== INPUT :\n', md_file,':')
        # uncomment next two lines if want to see raw input in console
        # print('\n', md_file.read())
        # md_file.seek(0)

        parser = mistune.BlockLexer()
        text = md_file.read()
        parser.parse(mistune.preprocessing(text))
        for t in parser.tokens:
            if t["type"] == "table":
                #print(t)
                if t["header"][0].lower() in KEYWORDS:
                    data = "| *" + "* | *".join(t["header"]) + "* |\n"
                    for l in t["cells"]:
                        data += "| " + " | ".join(l) + " |\n"
                    #print(data)
                    robot_data.write(data)

        with StringIO(text) as f:
        #print('\n========== TEMP :\n', f)
            include_line = False
            for line in f.readlines():
                if not include_line:
                    include_line = line.strip().lower() == "```robotframework"
                elif line.strip() == "```":
                    include_line = False
                else:
                    robot_lines.append(line)
            robot_data.write(''.join(robot_lines))
            return robot_data.getvalue()
