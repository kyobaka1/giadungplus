from django import template

register = template.Library()


@register.filter(name='tag_color')
def tag_color(tag_name):
    """
    Assign a consistent color to a tag based on its name.
    Uses hash of tag name to ensure same tag always gets same color.
    """
    # Define color palette
    colors = [
        'bg-purple-100 text-purple-700',
        'bg-pink-100 text-pink-700',
        'bg-indigo-100 text-indigo-700',
        'bg-cyan-100 text-cyan-700',
        'bg-teal-100 text-teal-700',
        'bg-amber-100 text-amber-700',
        'bg-rose-100 text-rose-700',
        'bg-emerald-100 text-emerald-700',
        'bg-sky-100 text-sky-700',
        'bg-violet-100 text-violet-700',
    ]
    
    # Use hash of tag name to get consistent color index
    color_index = hash(tag_name) % len(colors)
    return colors[color_index]
