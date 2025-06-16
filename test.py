import filetype

kind = filetype.guess('"D:\Project\DATN_HUST\ai-agent\data\tesst.txt"')
if kind is None:
    print('Cannot guess file type!')
else:
    print('File extension: %s' % kind.extension)
    print('File MIME type: %s' % kind.mime)