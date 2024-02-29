# TexelUniformityTool

TexelUniformityTool is a Blender add-on designed to do 3 things vanilla blender doesn't:
1. Apply smart UV Project in a way that it works correctly across all selected meshes (in vanilla blender it only works correctly for a single selected mesh.)
2. Calculate Texel density for a single selected mesh in px/cm
3. Set desired Texel Density to all selected meshes similar to #1


## Features

1. **Smart UV Project**: Apply Smart UV projection settings across multiple selected meshes, streamlining the UV mapping process.
2. **Texel Density Calculation**: Calculate the texel density for a single selected mesh.
3. **Texture Resolution Setting**: Set the texture resolution (1024, 2048, 4096, etc) for setting and calculating texel density for.
4. **Texel Density Setting**: Adjust the texel density for multiple selected meshes simultaneously, ensuring uniform texture detail across your scene.

## Installation

1. Download `TexelUniformityTool.py`.
2. Open Blender and navigate to `Edit > Preferences > Add-ons`.
3. Click `Install` and select the downloaded `.py` file.
4. Enable the add-on by ticking the checkbox next to its name.

## Usage

### Smart UV Project
1. Select the meshes you wish to apply the Smart UV Project to. (in Object mode!)
2. Access the tool via the Texel Uniformity panel in the 3D Viewport's sidebar (N key).
3. Adjust the Angle Limit and Island Margin as needed.
4. Click `Bulk Apply Smart UV Project`.

### Calculating Texel Density
1. Select a single mesh.
2. Ensure the texture resolution is set in the Texel Uniformity panel.
3. Click `Calculate Density` to view the current texel density for a single selected mesh.

### Setting Texel Density
1. Select the meshes you wish to set to desired texel density
2. Set the desired `Target Density` in the panel.
3. Click `Set Density` to apply the new texel density to all selected meshes.

## Support

For support, questions, or contributions, please visit the [[GitHub repository](<GitHub-Repo-URL>](https://github.com/artemmakeev/TexelUniformityTool))

## License

This project is licensed under the GPL License - see the LICENSE file for details.
