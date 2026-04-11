# YouTube

## How to Convert Excel, Word, PowerPoint & PDFs to Markdown with Python

### Video Metadata
- **Keywords:** excel to markdown python,word to markdown python,powerpoint to markdown python,pdf to markdown python,convert excel to markdown python,convert word to markdown python,convert powerpoint to markdown python,convert pdf to markdown python,python excel markdown,python word markdown,python powerpoint markdown,python pdf markdown,excel to markdown,word to markdown,powerpoint to markdown,pdf to markdown,markdown conversion python,python for document conversion
- **Runtime:** PT4M0S

### Description
👉 Excelソリューションをすべて見る: https://pythonandvba.com/solutions

𝗗𝗘𝗦𝗖𝗥𝗜𝗣𝗧𝗜𝗢𝗡
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
AIトレーニング用にOfficeドキュメントをMarkdown形式に変換しましょう！この動画では、Pythonライブラリ「markitdown」を使用して、PDF、Excel、Word、さらにはYouTubeデータを大規模言語モデルやカスタムGPTで使用できるように変換する方法を紹介します。
#LLM #ChatGPT #Markdown

🌍 参考資料:
▶ Office2MD Web アプリ: https://pythonandvba.com/office-to-ma...
▶ MarkItDown パッケージ: https://github.com/microsoft/markitdown

リンク集
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
🔗 LinkedIn:   / sven-bosau
📬 お問い合わせ: https://pythonandvba.com/contact

☕ 𝗕𝘂𝘆 𝗺𝗲 𝗮 𝗰𝗼𝗳𝗳𝗲𝗲？
このチャンネルを応援したい方は、こちらからコーヒーを買ってください。
▶ https://pythonandvba.com/coffee-donation

### Transcript
Large language models like OpenAI's ChatGPT really love Markdown Now, Markdown is very close to plain text, but it still gives important structure to a document So, if you are planning to train your own large language model or create a custom GPT inside ChatGPT using Office documents like Excel files, Word documents, PowerPoint slides or even PDF files, it is actually a smart idea to convert those Office documents first into Markdown and then use those Markdown files to upload them to your knowledge base And in this video, I'm going to show you a new Python library which makes this conversion so from Office documents into Markdown files, super easy And if you don't want to code it out yourself, I've also created a smart web application where you can just upload your files, click a button, and then the application will convert them to Markdown files for free So, without further ado, let us dive in The Python library is called MarkItDown and it's developed and maintained by Microsoft And just like mentioned, it supports all standard Office file types, but you can also convert zip files, YouTube URLs, and much more Using the package is super simple All you gotta do is to install it using pip, just like written here in the documentation So, I've already got it installed on my computer And with that, let me show you a quick demo of how it works Let's say I want to convert this PDF into Markdown So, to convert the PDF, you just need to input the library, initialize the Markdown object and call the convert method with the file path Once that is done, you can take the result and use it however you want In my case, I'm just printing it to the console So when I run the script, I can now see the output right here in the terminal And just like that, I've extracted all the text from the document Now you could use this text in your own workflows and process it further as needed Alright, now for the next example, I've got an Excel file Now this workbook has different sheets, like one sheet with sales data, and another one with a weekly sales report Now to convert this Excel file, I've actually also built a small web application using Streamlit Under the hood, this application now uses the Markdown package So all you have to do is to select your file and press this button here Then you will get a sneak peek of the file and an option to download the Markdown version So when I open that Markdown file, you will see each sheet name is now turned into an H2 heading, and the data is shown in a table format Now it might look a little bit confusing for you, but large language models actually work really well with this kind of format It helps them to understand the structure and the context of the file Also, as I mentioned earlier, this package doesn't just work with Office documents You can also, for example, pull in the description and the transcript of any YouTube video So for that, just paste in your YouTube URL into this tool here and then click this button Now if I download and open the Markdown file, here is what it looks like You will see a header saying that it's a YouTube video, followed by the video title and the metadata And then you will get the video description and below that you will have the full transcript So in a nutshell, I think this Python package is super handy if you're looking to train your own AI model or building your own custom GPTs inside ChatGPT So you can easily turn all kinds of different files you might have into Markdown and then use this structured and clean text to train the AI And by the way, you can also find the source code of the Streamlit application on GitHub I will leave the link to the repo in the description box below All right, so I hope you found this super quick video helpful And as always, thanks for watching and I will see you in the next video

## Transcript

- [0.00s] Large language models like OpenAI's ChatGPT really love Markdown
- [4.80s] Now, Markdown is very close to plain text, but it still gives important structure to
- [9.42s] a document
- [10.38s] So, if you are planning to train your own large language model or create a custom GPT
- [15.22s] inside ChatGPT using Office documents like Excel files, Word documents, PowerPoint slides
- [21.88s] or even PDF files, it is actually a smart idea to convert those Office documents first
- [27.96s] into Markdown and then use those Markdown files to upload them to your knowledge base
- [33.32s] And in this video, I'm going to show you a new Python library which makes this conversion
- [37.68s] so from Office documents into Markdown files, super easy
- [41.48s] And if you don't want to code it out yourself, I've also created a smart web application
- [45.96s] where you can just upload your files, click a button, and then the application will convert
- [51.22s] them to Markdown files for free
- [53.30s] So, without further ado, let us dive in
- [55.96s] The Python library is called MarkItDown and it's developed and maintained by Microsoft
- [61.06s] And just like mentioned, it supports all standard Office file types, but you can also convert
- [65.84s] zip files, YouTube URLs, and much more
- [68.94s] Using the package is super simple
- [71.28s] All you gotta do is to install it using pip, just like written here in the documentation
- [75.94s] So, I've already got it installed on my computer
- [78.68s] And with that, let me show you a quick demo of how it works
- [81.62s] Let's say I want to convert this PDF into Markdown
- [84.36s] So, to convert the PDF, you just need to input the library, initialize the Markdown object
- [90.72s] and call the convert method with the file path
- [93.56s] Once that is done, you can take the result and use it however you want
- [97.22s] In my case, I'm just printing it to the console
- [100.16s] So when I run the script, I can now see the output right here in the terminal
- [104.22s] And just like that, I've extracted all the text from the document
- [107.94s] Now you could use this text in your own workflows and process it further as needed
- [112.64s] Alright, now for the next example, I've got an Excel file
- [116.54s] Now this workbook has different sheets, like one sheet with sales data, and another one
- [121.52s] with a weekly sales report
- [123.30s] Now to convert this Excel file, I've actually also built a small web application using Streamlit
- [128.64s] Under the hood, this application now uses the Markdown package
- [132.32s] So all you have to do is to select your file and press this button here
- [136.88s] Then you will get a sneak peek of the file and an option to download the Markdown version
- [141.67s] So when I open that Markdown file, you will see each sheet name is now turned into an
- [145.96s] H2 heading, and the data is shown in a table format
- [149.82s] Now it might look a little bit confusing for you, but large language models actually work
- [154.72s] really well with this kind of format
- [156.86s] It helps them to understand the structure and the context of the file
- [160.48s] Also, as I mentioned earlier, this package doesn't just work with Office documents
- [164.88s] You can also, for example, pull in the description and the transcript of any YouTube video
- [169.60s] So for that, just paste in your YouTube URL into this tool here and then click this button
- [175.90s] Now if I download and open the Markdown file, here is what it looks like
- [180.72s] You will see a header saying that it's a YouTube video, followed by the video title and the
- [185.04s] metadata
- [185.94s] And then you will get the video description and below that you will have the full transcript
- [190.78s] So in a nutshell, I think this Python package is super handy if you're looking to train
- [195.12s] your own AI model or building your own custom GPTs inside ChatGPT
- [200.06s] So you can easily turn all kinds of different files you might have into Markdown and then
- [205.22s] use this structured and clean text to train the AI
- [208.44s] And by the way, you can also find the source code of the Streamlit application on GitHub
- [212.82s] I will leave the link to the repo in the description box below
- [216.00s] All right, so I hope you found this super quick video helpful
- [219.00s] And as always, thanks for watching and I will see you in the next video