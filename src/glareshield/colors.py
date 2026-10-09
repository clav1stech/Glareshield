import colorsys


def rgb_to_hs(rgb):
    hue,saturation,_ = colorsys.rgb_to_hsv(*(channel/255 for channel in rgb))
    return round(hue*360),round(saturation*100)


def rgb_to_xy(rgb,gamut=None):
    channels = [((c/255+.055)/1.055)**2.4 if c/255 > .04045 else c/255/12.92 for c in rgb]
    r,g,b = channels
    x = r*.664511+g*.154324+b*.162028
    y = r*.283881+g*.668433+b*.047685
    z = r*.000088+g*.072310+b*.986039
    total = x+y+z
    point = (x/total,y/total) if total else (0.0,0.0)
    return clamp_xy(point,gamut) if gamut and total else point


def clamp_xy(point,gamut):
    triangle = [(gamut[name]['x'],gamut[name]['y']) for name in ('red','green','blue')]
    def cross(a,b,p):
        return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    signs = [cross(triangle[i],triangle[(i+1)%3],point) for i in range(3)]
    if all(v >= 0 for v in signs) or all(v <= 0 for v in signs):
        return point
    candidates = []
    for i in range(3):
        a,b = triangle[i],triangle[(i+1)%3]
        dx,dy = b[0]-a[0],b[1]-a[1]
        length = dx*dx+dy*dy
        t = max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0
        candidates.append((a[0]+t*dx,a[1]+t*dy))
    return min(candidates,key=lambda p:(point[0]-p[0])**2+(point[1]-p[1])**2)
